import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { devicesAPI } from '../services/api';
import DashboardSidebar from '../components/dashboard/DashboardSidebar';
import {
  ScrollText,
  Search,
  RefreshCw,
  Copy,
  Check,
  Smartphone,
  ArrowLeft,
  Wifi,
  WifiOff,
  Clock,
  Globe
} from 'lucide-react';

interface ConnectionLog {
  id: number | string;
  device_id: string;
  device_name: string;
  device_model: string;
  is_online: boolean;
  event: 'CONNECTED' | 'DISCONNECTED' | string;
  ip_address: string;
  timestamp: string;
  created_at: string;
}

interface SystemLogsPageProps {
  onLogout: () => void;
}

export default function SystemLogsPage({ onLogout }: SystemLogsPageProps) {
  const navigate = useNavigate();
  const [logs, setLogs] = useState<ConnectionLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedDevice, setSelectedDevice] = useState<string>('ALL');
  const [selectedEventType, setSelectedEventType] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [copiedId, setCopiedId] = useState<number | string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await devicesAPI.getConnectionLogs(300);
      setLogs(data || []);
    } catch (err) {
      console.error('Erro ao buscar logs de conexão:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchLogs]);

  // Lista única de dispositivos
  const uniqueDevices = Array.from(
    new Map(
      logs.map((item) => [
        item.device_id,
        { id: item.device_id, name: item.device_name, isOnline: item.is_online },
      ])
    ).values()
  );

  // Filtragem
  const filteredLogs = logs.filter((log) => {
    if (selectedDevice !== 'ALL' && log.device_id !== selectedDevice) return false;
    
    if (selectedEventType === 'CONNECTED' && log.event !== 'CONNECTED') return false;
    if (selectedEventType === 'DISCONNECTED' && log.event !== 'DISCONNECTED') return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const name = (log.device_name || '').toLowerCase();
      const id = (log.device_id || '').toLowerCase();
      const model = (log.device_model || '').toLowerCase();
      const ip = (log.ip_address || '').toLowerCase();
      return name.includes(q) || id.includes(q) || model.includes(q) || ip.includes(q);
    }

    return true;
  });

  // Estatísticas
  const totalCount = logs.length;
  const connectedCount = logs.filter((l) => l.event === 'CONNECTED').length;
  const disconnectedCount = logs.filter((l) => l.event === 'DISCONNECTED').length;
  const onlineDevicesNow = uniqueDevices.filter((d) => d.isOnline).length;

  const handleCopy = (text: string, id: number | string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const formatDate = (isoStr: string) => {
    if (!isoStr) return '--:--';
    try {
      const date = new Date(isoStr);
      return date.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return isoStr;
    }
  };

  const getTimeAgo = (isoStr: string) => {
    if (!isoStr) return '';
    try {
      const diff = Math.floor((new Date().getTime() - new Date(isoStr).getTime()) / 1000);
      if (diff < 60) return `${diff}s atrás`;
      if (diff < 3600) return `${Math.floor(diff / 60)}m atrás`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}h atrás`;
      return `${Math.floor(diff / 86400)}d atrás`;
    } catch {
      return '';
    }
  };

  return (
    <div className="flex h-screen bg-[#020714] text-slate-100 overflow-hidden font-sans selection:bg-cyan-500 selection:text-black">
      <DashboardSidebar onLogout={onLogout} />

      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-gradient-to-b from-[#020714] via-[#071126] to-[#020714]">
        {/* Header */}
        <header className="sticky top-0 z-30 bg-[#070d1e]/95 backdrop-blur-xl border-b border-cyan-500/30 px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-[0_0_20px_rgba(0,240,255,0.15)]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="p-2.5 rounded-xl bg-cyan-950/60 border-2 border-cyan-500/40 text-cyan-300 hover:bg-cyan-900/80 hover:text-white transition-all shadow-[0_0_12px_rgba(0,240,255,0.2)]"
              title="Voltar ao Dashboard"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>

            <div>
              <div className="flex items-center gap-2">
                <ScrollText className="w-6 h-6 text-cyan-400 drop-shadow-[0_0_10px_rgba(0,240,255,0.9)]" />
                <h1 className="text-xl font-black tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-teal-200 to-emerald-300 uppercase">
                  Logs do Sistema & Conexões
                </h1>
              </div>
              <p className="text-xs font-bold text-slate-300 mt-0.5">
                Histórico detalhado de entrada (conexão) e saída (desconexão) de cada aparelho
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Toggle Auto-Refresh */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl border-2 text-xs font-black transition-all ${
                autoRefresh
                  ? 'bg-cyan-950/80 border-cyan-500/60 text-cyan-200 shadow-[0_0_15px_rgba(0,240,255,0.3)]'
                  : 'bg-slate-900/80 border-slate-700/60 text-slate-400 hover:text-slate-200'
              }`}
            >
              <span className={`w-2.5 h-2.5 rounded-full ${autoRefresh ? 'bg-cyan-400 shadow-[0_0_8px_rgba(0,240,255,1)] animate-pulse' : 'bg-slate-500'}`} />
              Auto-Refresh (5s)
            </button>

            {/* Refresh manual */}
            <button
              onClick={fetchLogs}
              disabled={loading}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 via-teal-400 to-emerald-400 hover:from-cyan-400 hover:to-emerald-300 text-black font-black text-xs uppercase tracking-wider shadow-[0_0_20px_rgba(0,240,255,0.4)] transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </button>
          </div>
        </header>

        {/* Content Body */}
        <main className="p-6 space-y-6 max-w-7xl mx-auto w-full">
          {/* Top Cards de Estatísticas */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Card Total */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-cyan-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(0,240,255,0.15)] relative overflow-hidden group hover:border-cyan-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-cyan-400 shadow-[0_0_10px_rgba(0,240,255,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-cyan-300 uppercase tracking-widest">Total de Eventos</span>
                <ScrollText className="w-5 h-5 text-cyan-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(0,240,255,0.8)]" />
              </div>
              <div className="text-3xl font-black text-white mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(0,240,255,0.4)]">{totalCount}</div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Registros salvos</span>
            </div>

            {/* Card Conectados */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-emerald-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(16,185,129,0.15)] relative overflow-hidden group hover:border-emerald-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-emerald-300 uppercase tracking-widest">Conexões (Online)</span>
                <Wifi className="w-5 h-5 text-emerald-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              </div>
              <div className="text-3xl font-black text-emerald-200 mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(16,185,129,0.4)]">{connectedCount}</div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Aparelhos conectados</span>
            </div>

            {/* Card Desconectados */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-rose-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(244,63,94,0.15)] relative overflow-hidden group hover:border-rose-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-rose-400 shadow-[0_0_10px_rgba(244,63,94,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-rose-300 uppercase tracking-widest">Desconexões</span>
                <WifiOff className="w-5 h-5 text-rose-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(244,63,94,0.8)]" />
              </div>
              <div className="text-3xl font-black text-rose-200 mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(244,63,94,0.4)]">{disconnectedCount}</div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Quedas / saídas de rede</span>
            </div>

            {/* Card Aparelhos Online Agora */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-teal-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(20,184,166,0.15)] relative overflow-hidden group hover:border-teal-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-teal-400 shadow-[0_0_10px_rgba(20,184,166,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-teal-300 uppercase tracking-widest">Online Agora</span>
                <Smartphone className="w-5 h-5 text-teal-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(20,184,166,0.8)]" />
              </div>
              <div className="text-3xl font-black text-teal-100 mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(20,184,166,0.4)]">{onlineDevicesNow}</div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Aparelhos ativos</span>
            </div>
          </div>

          {/* Filtros e Busca */}
          <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-cyan-500/30 rounded-2xl p-4 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4 shadow-xl">
            {/* Campo de Busca */}
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-cyan-400 absolute left-4 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Buscar por nome do aparelho, modelo, ID ou IP..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#020714]/95 border-2 border-cyan-500/40 rounded-xl pl-11 pr-4 py-2.5 text-xs font-bold text-cyan-100 placeholder:text-slate-400 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/40 font-mono transition-all shadow-[0_0_15px_rgba(0,240,255,0.1)]"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {/* Filtro por Aparelho */}
              <div className="flex items-center gap-2">
                <Smartphone className="w-4 h-4 text-cyan-400 hidden sm:block" />
                <select
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                  className="bg-[#020714] border-2 border-cyan-500/40 rounded-xl px-4 py-2 text-xs font-black text-cyan-200 focus:outline-none focus:border-cyan-400 font-mono"
                >
                  <option value="ALL">Todos os Aparelhos ({uniqueDevices.length})</option>
                  {uniqueDevices.map((dev) => (
                    <option key={dev.id} value={dev.id}>
                      {dev.isOnline ? '🟢' : '🔴'} {dev.name} ({dev.id.substring(0, 8)})
                    </option>
                  ))}
                </select>
              </div>

              {/* Filtro por Tipo de Evento */}
              <div className="flex items-center gap-2">
                <select
                  value={selectedEventType}
                  onChange={(e) => setSelectedEventType(e.target.value)}
                  className="bg-[#020714] border-2 border-cyan-500/40 rounded-xl px-4 py-2 text-xs font-black text-cyan-200 focus:outline-none focus:border-cyan-400 font-mono"
                >
                  <option value="ALL">Todos os Eventos</option>
                  <option value="CONNECTED">🟢 Apenas Conectados</option>
                  <option value="DISCONNECTED">🔴 Apenas Desconectados</option>
                </select>
              </div>
            </div>
          </div>

          {/* Tabela de Logs */}
          <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-cyan-500/30 rounded-2xl overflow-hidden shadow-2xl">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b-2 border-cyan-500/30 bg-[#020714]/95 text-xs uppercase tracking-wider text-cyan-300 font-black font-mono">
                    <th className="py-4 px-5">Data / Hora</th>
                    <th className="py-4 px-5">Dispositivo</th>
                    <th className="py-4 px-5">Evento de Rede</th>
                    <th className="py-4 px-5">Status Atual</th>
                    <th className="py-4 px-5">Endereço IP</th>
                    <th className="py-4 px-5 text-right">Ação</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-cyan-500/15 text-xs font-bold font-mono">
                  {loading && filteredLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-16 text-center text-cyan-300">
                        <div className="flex flex-col items-center justify-center gap-3">
                          <RefreshCw className="w-8 h-8 animate-spin text-cyan-400 drop-shadow-[0_0_10px_rgba(0,240,255,0.8)]" />
                          <span className="text-sm font-black uppercase tracking-wider">Carregando logs de conexão...</span>
                        </div>
                      </td>
                    </tr>
                  ) : filteredLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-16 text-center text-slate-300">
                        <div className="flex flex-col items-center justify-center gap-2">
                          <ScrollText className="w-10 h-10 text-cyan-400/50 mb-2 animate-pulse" />
                          <span className="text-base font-black text-white">Nenhum Registro Encontrado</span>
                          <span className="text-xs text-slate-400 font-bold max-w-sm">Nenhum evento de conexão ou desconexão bate com os filtros atuais.</span>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    filteredLogs.map((log) => {
                      const isConnected = log.event === 'CONNECTED';
                      return (
                        <tr
                          key={log.id}
                          className="hover:bg-cyan-950/40 transition-colors group"
                        >
                          {/* Data / Hora */}
                          <td className="py-4 px-5 whitespace-nowrap text-white font-black">
                            <div className="flex items-center gap-2">
                              <Clock className="w-4 h-4 text-cyan-400 drop-shadow-[0_0_6px_rgba(0,240,255,0.6)]" />
                              <span>{formatDate(log.timestamp)}</span>
                              <span className="text-xs font-bold text-cyan-300/80">({getTimeAgo(log.timestamp)})</span>
                            </div>
                          </td>

                          {/* Dispositivo */}
                          <td className="py-4 px-5">
                            <div className="flex items-center gap-3">
                              <div className="w-9 h-9 rounded-xl bg-cyan-950/70 border-2 border-cyan-500/40 flex items-center justify-center text-cyan-300 shrink-0 shadow-[0_0_10px_rgba(0,240,255,0.2)]">
                                <Smartphone className="w-4 h-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="font-black text-sm text-white truncate group-hover:text-cyan-300 transition-colors">
                                  {log.device_name}
                                </div>
                                <div className="text-xs font-bold text-cyan-300/80 truncate">
                                  {log.device_model} • <span className="font-mono font-bold text-cyan-400">{log.device_id}</span>
                                </div>
                              </div>
                            </div>
                          </td>

                          {/* Evento */}
                          <td className="py-4 px-5 whitespace-nowrap">
                            {isConnected ? (
                              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/20 border-2 border-emerald-500/50 text-emerald-300 text-xs font-black tracking-wider shadow-[0_0_12px_rgba(16,185,129,0.25)]">
                                <Wifi className="w-4 h-4 text-emerald-300" />
                                CONECTADO (Entrou)
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-500/20 border-2 border-rose-500/50 text-rose-300 text-xs font-black tracking-wider shadow-[0_0_12px_rgba(244,63,94,0.25)]">
                                <WifiOff className="w-4 h-4 text-rose-300" />
                                DESCONECTADO (Saiu)
                              </span>
                            )}
                          </td>

                          {/* Status Atual do Aparelho */}
                          <td className="py-4 px-5 whitespace-nowrap">
                            <span className="inline-flex items-center gap-2 text-white font-black text-xs">
                              <span
                                className={`w-2.5 h-2.5 rounded-full ${
                                  log.is_online
                                    ? 'bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,1)] animate-pulse'
                                    : 'bg-slate-600'
                                }`}
                              />
                              {log.is_online ? 'ONLINE AGORA' : 'OFFLINE'}
                            </span>
                          </td>

                          {/* IP Address */}
                          <td className="py-4 px-5 whitespace-nowrap text-white font-black">
                            <div className="flex items-center gap-2 font-mono text-xs">
                              <Globe className="w-4 h-4 text-slate-400" />
                              <span className="text-cyan-200">{log.ip_address || '127.0.0.1'}</span>
                            </div>
                          </td>

                          {/* Botão Copiar */}
                          <td className="py-4 px-5 text-right whitespace-nowrap">
                            <button
                              onClick={() =>
                                handleCopy(
                                  `Dispositivo: ${log.device_name} (${log.device_id})\nEvento: ${log.event}\nData: ${formatDate(log.timestamp)}\nIP: ${log.ip_address}`,
                                  log.id
                                )
                              }
                              className="p-2 rounded-xl bg-cyan-950/70 border-2 border-cyan-500/40 text-cyan-300 hover:bg-cyan-900/80 hover:text-white transition-all shadow-[0_0_10px_rgba(0,240,255,0.2)]"
                              title="Copiar Detalhes do Log"
                            >
                              {copiedId === log.id ? (
                                <Check className="w-4 h-4 text-emerald-300" />
                              ) : (
                                <Copy className="w-4 h-4" />
                              )}
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
