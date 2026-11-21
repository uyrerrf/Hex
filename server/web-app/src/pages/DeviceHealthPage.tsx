import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { devicesAPI } from '../services/api';
import DashboardSidebar from '../components/dashboard/DashboardSidebar';
import {
  Activity,
  Search,
  RefreshCw,
  Smartphone,
  ArrowLeft,
  WifiOff,
  Zap,
  Battery,
  BatteryCharging,
  Radio,
  ExternalLink,
  AlertTriangle,
  Globe
} from 'lucide-react';

interface DeviceHealthItem {
  device_id: string;
  custom_name: string;
  model: string;
  manufacturer: string;
  android_version: string;
  is_online: boolean;
  ip_address: string;
  ping_ms: number | null;
  status_label: 'EXCELENTE' | 'BOM' | 'REGULAR' | 'OFFLINE' | string;
  battery_level: number;
  is_charging: boolean;
  network_type: string;
  sim_operator: string;
  last_seen: string | null;
  seconds_since_active: number;
}

interface DeviceHealthPageProps {
  onLogout: () => void;
}

export default function DeviceHealthPage({ onLogout }: DeviceHealthPageProps) {
  const navigate = useNavigate();
  const [devices, setDevices] = useState<DeviceHealthItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterStatus, setFilterStatus] = useState<string>('ONLINE');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [pingingDeviceId, setPingingDeviceId] = useState<string | null>(null);
  const [reconnectingDeviceId, setReconnectingDeviceId] = useState<string | null>(null);
  const [measuredPings, setMeasuredPings] = useState<Record<string, number>>({});
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      const data = await devicesAPI.getDevicesHealth();
      setDevices(data || []);
    } catch (err) {
      console.error('Erro ao buscar status de saúde e pings:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchHealth]);

  // Função para medir ping interativo individual
  const handlePingDevice = async (deviceId: string) => {
    try {
      setPingingDeviceId(deviceId);
      const res = await devicesAPI.pingDevice(deviceId);
      if (res && typeof res.ping_ms === 'number') {
        setMeasuredPings((prev) => ({ ...prev, [deviceId]: res.ping_ms }));
        showToast('Ping medido em tempo real com sucesso!');
      }
    } catch (err) {
      console.error('Erro ao medir ping:', err);
    } finally {
      setPingingDeviceId(null);
    }
  };

  // Função para reiniciar conexão WebSocket do dispositivo
  const handleReconnectDevice = async (deviceId: string, customName: string) => {
    try {
      setReconnectingDeviceId(deviceId);
      await devicesAPI.reconnectDevice(deviceId);
      showToast(`🔄 Comando enviado: Reiniciando conexão de ${customName}...`);
      setTimeout(() => {
        fetchHealth();
      }, 2500);
    } catch (err) {
      console.error('Erro ao reiniciar conexão:', err);
      showToast('❌ Falha ao enviar comando de reconexão.');
    } finally {
      setReconnectingDeviceId(null);
    }
  };

  // Filtragem
  const filteredDevices = devices.filter((dev) => {
    if (filterStatus === 'ONLINE' && !dev.is_online) return false;
    if (filterStatus === 'OFFLINE' && dev.is_online) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const name = (dev.custom_name || '').toLowerCase();
      const model = (dev.model || '').toLowerCase();
      const id = (dev.device_id || '').toLowerCase();
      const ip = (dev.ip_address || '').toLowerCase();
      return name.includes(q) || model.includes(q) || id.includes(q) || ip.includes(q);
    }

    return true;
  });

  // Métricas gerais
  const totalCount = devices.length;
  const onlineCount = devices.filter((d) => d.is_online).length;
  const offlineCount = totalCount - onlineCount;

  // Média de Ping
  const onlinePings = devices
    .filter((d) => d.is_online)
    .map((d) => measuredPings[d.device_id] ?? d.ping_ms ?? 35);
  const avgPing =
    onlinePings.length > 0
      ? Math.round(onlinePings.reduce((a, b) => a + b, 0) / onlinePings.length)
      : 0;

  // Média de Bateria
  const avgBattery =
    devices.length > 0
      ? Math.round(devices.reduce((a, b) => a + (b.battery_level || 0), 0) / devices.length)
      : 0;

  const getPingBadge = (ping: number | null, isOnline: boolean) => {
    if (!isOnline || ping === null) {
      return {
        bg: 'bg-rose-500/20 border-2 border-rose-500/50 text-rose-300 shadow-[0_0_12px_rgba(244,63,94,0.3)]',
        label: 'OFFLINE',
        icon: WifiOff,
      };
    }
    if (ping < 50) {
      return {
        bg: 'bg-cyan-500/20 border-2 border-cyan-500/50 text-cyan-300 shadow-[0_0_15px_rgba(0,240,255,0.3)]',
        label: `${ping} ms • EXCELENTE`,
        icon: Zap,
      };
    }
    if (ping < 150) {
      return {
        bg: 'bg-sky-500/20 border-2 border-sky-500/50 text-sky-300 shadow-[0_0_15px_rgba(56,189,248,0.3)]',
        label: `${ping} ms • BOM`,
        icon: Zap,
      };
    }
    return {
      bg: 'bg-amber-500/20 border-2 border-amber-500/50 text-amber-300 shadow-[0_0_15px_rgba(245,158,11,0.3)]',
      label: `${ping} ms • INSTÁVEL`,
      icon: AlertTriangle,
    };
  };

  const getBatteryColor = (level: number) => {
    if (level > 50) return 'text-cyan-400 bg-cyan-400';
    if (level > 20) return 'text-amber-400 bg-amber-400';
    return 'text-rose-400 bg-rose-500';
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
              title="Back to Dashboard"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>

            <div>
              <div className="flex items-center gap-2">
                <Activity className="w-6 h-6 text-cyan-400 drop-shadow-[0_0_10px_rgba(0,240,255,0.9)]" />
                <h1 className="text-xl font-black tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-sky-300 to-blue-400 uppercase">
                  Pings & Device Management
                </h1>
              </div>
              <p className="text-xs font-bold text-slate-300 mt-0.5">
                Monitoramento em tempo real da saúde, sinal, bateria e latência (ping) de cada dispositivo
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
              onClick={fetchHealth}
              disabled={loading}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 via-sky-400 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-black font-black text-xs uppercase tracking-wider shadow-[0_0_20px_rgba(0,240,255,0.4)] transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </header>

        {/* Content Body */}
        <main className="p-6 space-y-6 max-w-7xl mx-auto w-full">
          {/* Toast Banner */}
          {toastMessage && (
            <div className="bg-cyan-950/90 border-2 border-cyan-400 text-cyan-200 px-4 py-3 rounded-xl shadow-[0_0_20px_rgba(0,240,255,0.4)] flex items-center justify-between font-mono text-xs font-bold">
              <div className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
                <span>{toastMessage}</span>
              </div>
              <button onClick={() => setToastMessage(null)} className="text-cyan-400 hover:text-white font-bold ml-4">✕</button>
            </div>
          )}

          {/* Top Cards de Estatísticas */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Online/Total */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-cyan-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(0,240,255,0.15)] relative overflow-hidden group hover:border-cyan-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-cyan-400 shadow-[0_0_10px_rgba(0,240,255,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-cyan-300 uppercase tracking-widest">Deviceos Ativos</span>
                <Smartphone className="w-5 h-5 text-cyan-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(0,240,255,0.8)]" />
              </div>
              <div className="text-3xl font-black text-white mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(0,240,255,0.4)]">
                {onlineCount} <span className="text-xs font-bold text-cyan-300/80">/ {totalCount} online</span>
              </div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Connected to C&C</span>
            </div>

            {/* Latência Média */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-sky-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(56,189,248,0.15)] relative overflow-hidden group hover:border-sky-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-sky-400 shadow-[0_0_10px_rgba(56,189,248,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-sky-300 uppercase tracking-widest">Ping Médio</span>
                <Zap className="w-5 h-5 text-sky-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(56,189,248,0.8)]" />
              </div>
              <div className="text-3xl font-black text-sky-200 mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(56,189,248,0.4)]">
                {avgPing > 0 ? `${avgPing} ms` : '--'}
              </div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Resposta da rede</span>
            </div>

            {/* Média Bateria */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-blue-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(59,130,246,0.15)] relative overflow-hidden group hover:border-blue-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-blue-400 shadow-[0_0_10px_rgba(59,130,246,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-blue-300 uppercase tracking-widest">Carga Média</span>
                <Battery className="w-5 h-5 text-blue-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(59,130,246,0.8)]" />
              </div>
              <div className="text-3xl font-black text-blue-100 mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(59,130,246,0.4)]">
                {avgBattery}%
              </div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Nível de bateria</span>
            </div>

            {/* Offline */}
            <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-rose-500/40 rounded-2xl p-5 shadow-[0_0_25px_rgba(244,63,94,0.15)] relative overflow-hidden group hover:border-rose-400 transition-all">
              <div className="absolute top-0 left-0 w-1.5 h-full bg-rose-400 shadow-[0_0_10px_rgba(244,63,94,0.8)]" />
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-rose-300 uppercase tracking-widest">Offline</span>
                <WifiOff className="w-5 h-5 text-rose-300 group-hover:scale-110 transition-transform drop-shadow-[0_0_8px_rgba(244,63,94,0.8)]" />
              </div>
              <div className="text-3xl font-black text-rose-200 mt-2 font-mono tracking-tight drop-shadow-[0_0_10px_rgba(244,63,94,0.4)]">
                {offlineCount}
              </div>
              <span className="text-xs font-bold text-slate-300 mt-1 block">Sem resposta</span>
            </div>
          </div>

          {/* Filtros e Busca */}
          <div className="bg-[#071126]/95 backdrop-blur-xl border-2 border-cyan-500/30 rounded-2xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-xl">
            <div className="relative flex-1 w-full">
              <Search className="w-4 h-4 text-cyan-400 absolute left-4 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Buscar por nome, modelo, ID do aparelho ou IP..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#020714]/95 border-2 border-cyan-500/40 rounded-xl pl-11 pr-4 py-2.5 text-xs font-bold text-cyan-100 placeholder:text-slate-400 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/40 font-mono transition-all shadow-[0_0_15px_rgba(0,240,255,0.1)]"
              />
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto">
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="bg-[#020714] border-2 border-cyan-500/40 rounded-xl px-4 py-2.5 text-xs font-black text-cyan-200 focus:outline-none focus:border-cyan-400 font-mono w-full sm:w-auto shadow-md"
              >
                <option value="ALL">Todos os Deviceos ({totalCount})</option>
                <option value="ONLINE">🔵 Apenas Online ({onlineCount})</option>
                <option value="OFFLINE">🔴 Apenas Offline ({offlineCount})</option>
              </select>
            </div>
          </div>

          {/* Grid de Dispositivos */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {loading && devices.length === 0 ? (
              <div className="col-span-full py-20 text-center bg-[#071126]/90 backdrop-blur-xl rounded-2xl border-2 border-cyan-500/30 shadow-[0_0_30px_rgba(0,240,255,0.1)]">
                <RefreshCw className="w-10 h-10 animate-spin text-cyan-400 mx-auto mb-3 drop-shadow-[0_0_12px_rgba(0,240,255,0.8)]" />
                <h3 className="text-base font-black text-white uppercase tracking-wider">Carregando Situação dos Deviceos...</h3>
              </div>
            ) : filteredDevices.length === 0 ? (
              <div className="col-span-full py-16 text-center bg-[#071126]/95 backdrop-blur-xl rounded-2xl border-2 border-cyan-500/30 p-8 shadow-[0_0_30px_rgba(0,240,255,0.1)]">
                <Smartphone className="w-12 h-12 text-cyan-400 mx-auto mb-3 animate-pulse drop-shadow-[0_0_15px_rgba(0,240,255,0.8)]" />
                <h3 className="text-lg font-black text-white uppercase tracking-wider">Nenhum Dispositivo Encontrado</h3>
                <p className="text-xs font-bold text-cyan-300 mt-1 max-w-md mx-auto">
                  {searchQuery || filterStatus !== 'ALL'
                    ? 'Nenhum dispositivo corresponde aos filtros aplicados.'
                    : 'Aguardando dispositivos Android ativos se conectarem ao servidor C&C...'}
                </p>
              </div>
            ) : (
              filteredDevices.map((dev) => {
                const livePing = measuredPings[dev.device_id] ?? dev.ping_ms;
                const pingInfo = getPingBadge(livePing, dev.is_online);
                const PingIcon = pingInfo.icon;
                const isPinging = pingingDeviceId === dev.device_id;
                const batColor = getBatteryColor(dev.battery_level);

                return (
                  <div
                    key={dev.device_id}
                    className={`bg-[#071126]/95 backdrop-blur-xl border-2 rounded-2xl p-5 flex flex-col justify-between transition-all duration-300 hover:scale-[1.02] ${
                      dev.is_online
                        ? 'border-cyan-500/50 shadow-[0_0_25px_rgba(0,240,255,0.15)] hover:border-cyan-400'
                        : 'border-slate-800/90 opacity-85'
                    }`}
                  >
                    {/* Header Card */}
                    <div>
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-11 h-11 rounded-xl bg-cyan-950/70 border-2 border-cyan-500/50 flex items-center justify-center text-cyan-300 shrink-0 shadow-[0_0_15px_rgba(0,240,255,0.3)]">
                            <Smartphone className="w-5 h-5" />
                          </div>
                          <div className="min-w-0">
                            <h3 className="font-black text-base text-white truncate tracking-wide">
                              {dev.custom_name}
                            </h3>
                            <p className="text-xs font-bold text-cyan-300/90 truncate">
                              {dev.model} • Android {dev.android_version}
                            </p>
                          </div>
                        </div>

                        {/* Badge de Status Online/Offline */}
                        <span
                          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border-2 text-[11px] font-black tracking-wider shrink-0 ${pingInfo.bg}`}
                        >
                          <PingIcon className="w-3.5 h-3.5" />
                          {pingInfo.label}
                        </span>
                      </div>

                      {/* Informações de Saúde em Linha */}
                      <div className="space-y-3 my-4 bg-[#020714]/90 rounded-xl p-3.5 border border-cyan-500/20 text-xs font-mono shadow-inner">
                        {/* Ping / Resposta */}
                        <div className="flex items-center justify-between">
                          <span className="text-slate-300 font-bold flex items-center gap-1.5">
                            <Zap className="w-4 h-4 text-cyan-400" /> Latência (Ping):
                          </span>
                          <span className="font-black text-sm text-cyan-300 drop-shadow-[0_0_6px_rgba(0,240,255,0.6)]">
                            {dev.is_online ? `${livePing ?? 35} ms` : 'Offline'}
                          </span>
                        </div>

                        {/* Nível de Bateria */}
                        <div className="flex items-center justify-between">
                          <span className="text-slate-300 font-bold flex items-center gap-1.5">
                            {dev.is_charging ? (
                              <BatteryCharging className="w-4 h-4 text-cyan-400" />
                            ) : (
                              <Battery className="w-4 h-4 text-slate-300" />
                            )}
                            Bateria:
                          </span>
                          <div className="flex items-center gap-2">
                            <div className="w-20 h-2.5 bg-slate-800 rounded-full overflow-hidden border border-cyan-500/20">
                              <div
                                className={`h-full ${batColor.split(' ')[1]}`}
                                style={{ width: `${dev.battery_level}%` }}
                              />
                            </div>
                            <span className="font-black text-white text-xs">
                              {dev.battery_level}% {dev.is_charging ? '⚡' : ''}
                            </span>
                          </div>
                        </div>

                        {/* Conexão / Sinal */}
                        <div className="flex items-center justify-between">
                          <span className="text-slate-300 font-bold flex items-center gap-1.5">
                            <Radio className="w-4 h-4 text-cyan-400" /> Rede / Operadora:
                          </span>
                          <span className="font-bold text-white truncate max-w-[150px]" title={dev.network_type}>
                            {dev.network_type} ({dev.sim_operator})
                          </span>
                        </div>

                        {/* Endereço IP */}
                        <div className="flex items-center justify-between">
                          <span className="text-slate-300 font-bold flex items-center gap-1.5">
                            <Globe className="w-4 h-4 text-slate-400" /> Endereço IP:
                          </span>
                          <span className="font-bold text-cyan-200 text-xs">{dev.ip_address}</span>
                        </div>
                      </div>
                    </div>

                    {/* Footer Card - Ações */}
                    <div className="pt-3 border-t border-cyan-500/20 flex flex-wrap items-center justify-between gap-2">
                      {/* Botão Testar Ping Agora */}
                      <button
                        onClick={() => handlePingDevice(dev.device_id)}
                        disabled={!dev.is_online || isPinging}
                        className="flex-1 min-w-[90px] flex items-center justify-center gap-1 py-2 px-2.5 rounded-xl bg-cyan-950/80 border-2 border-cyan-500/50 text-cyan-200 hover:bg-cyan-900 hover:border-cyan-400 font-black text-[11px] uppercase tracking-wider transition-all shadow-[0_0_12px_rgba(0,240,255,0.2)] disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <Zap className={`w-3.5 h-3.5 ${isPinging ? 'animate-bounce text-cyan-400' : ''}`} />
                        {isPinging ? 'Medindo...' : 'Ping'}
                      </button>

                      {/* Botão Reiniciar Conexão */}
                      <button
                        onClick={() => handleReconnectDevice(dev.device_id, dev.custom_name)}
                        disabled={!dev.is_online || reconnectingDeviceId === dev.device_id}
                        className="flex-1 min-w-[125px] flex items-center justify-center gap-1.5 py-2 px-2.5 rounded-xl bg-amber-950/80 border-2 border-amber-500/60 text-amber-300 hover:bg-amber-900 hover:border-amber-400 font-black text-[11px] uppercase tracking-wider transition-all shadow-[0_0_12px_rgba(245,158,11,0.2)] disabled:opacity-40 disabled:cursor-not-allowed"
                        title="Envia comando para o aparelho reiniciar e reconectar o WebSocket"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${reconnectingDeviceId === dev.device_id ? 'animate-spin text-amber-400' : ''}`} />
                        {reconnectingDeviceId === dev.device_id ? 'Reiniciando...' : 'Reiniciar Conexão'}
                      </button>

                      {/* Botão Abrir Controle */}
                      <button
                        onClick={() => navigate(`/device/${dev.device_id}`)}
                        className="flex items-center justify-center gap-1 py-2 px-3 rounded-xl bg-gradient-to-r from-cyan-500 via-sky-400 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-black font-black text-[11px] uppercase tracking-wider transition-all shadow-[0_0_15px_rgba(0,240,255,0.3)] shrink-0"
                      >
                        Painel
                        <ExternalLink className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
