import { useState } from 'react';
import { authAPI } from '../services/api';
import { User, Lock, Key, Loader, Eye, EyeOff, ShieldCheck, QrCode, Copy, CheckCircle2, ArrowLeft, Zap, Mail, Sparkles, Send } from 'lucide-react';
import LanguageSelector from '../components/LanguageSelector';
import { useTranslation } from '../utils/i18n';

interface LoginPageProps {
  onLogin: (token: string) => void;
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const { t } = useTranslation();
  const [isTrialMode, setIsTrialMode] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [telegram, setTelegram] = useState('');
  const [email, setEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [hwid, setHwid] = useState('');
  const [needsHwid, setNeedsHwid] = useState(false);
  
  // 2FA Google Authenticator states
  const [needs2FA, setNeeds2FA] = useState(false);
  const [needs2FASetup, setNeeds2FASetup] = useState(false);
  const [totpSecret, setTotpSecret] = useState('');
  const [totpQrCode, setTotpQrCode] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [twoFactorToken, setTwoFactorToken] = useState('');
  const [copiedSecret, setCopiedSecret] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const generateHWID = () => {
    const nav = window.navigator;
    const screen = window.screen;
    let string = nav.userAgent + nav.language + screen.colorDepth + screen.width + screen.height;
    
    let hash = 0;
    for (let i = 0; i < string.length; i++) {
      const char = string.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return 'WEB-' + Math.abs(hash).toString(16).toUpperCase();
  };

  const resetAll2FAStates = () => {
    setNeeds2FA(false);
    setNeeds2FASetup(false);
    setNeedsHwid(false);
    setTotpSecret('');
    setTotpQrCode('');
    setTotpCode('');
    setTwoFactorToken('');
    setError('');
  };

  const handleCopySecret = () => {
    if (totpSecret) {
      navigator.clipboard.writeText(totpSecret);
      setCopiedSecret(true);
      setTimeout(() => setCopiedSecret(false), 2000);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const currentHwid = generateHWID();
      setHwid(currentHwid);

      const response = await authAPI.login({
        username: username.trim(),
        password: password.trim(),
        hwid: currentHwid
      });

      if (response.two_factor_token) {
        setTwoFactorToken(response.two_factor_token);
      }

      if (response.requires_2fa_setup || response.needs_2fa_setup) {
        setNeeds2FASetup(true);
        setTotpSecret(response.secret || '');
        setTotpQrCode(response.qr_code || '');
        return;
      }

      if (response.requires_2fa || response.needs_2fa) {
        setNeeds2FA(true);
        return;
      }

      onLogin(response.access_token);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      let detailStr = '';
      if (typeof detail === 'string') {
        detailStr = detail;
      } else if (Array.isArray(detail)) {
        detailStr = detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join(', ');
      } else if (detail?.msg) {
        detailStr = detail.msg;
      }
      
      const isHWIDError = detailStr.toLowerCase().includes('hwid') || 
                         detailStr.toLowerCase().includes('dispositivo') || 
                         detailStr.toLowerCase().includes('hardware');

      if (isHWIDError) {
        setNeedsHwid(true);
      } else {
        setError(detailStr || 'Erro ao realizar login');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterTrial = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!telegram.trim()) {
      setError('Por favor, informe seu Telegram.');
      return;
    }

    setLoading(true);

    try {
      const currentHwid = generateHWID();
      setHwid(currentHwid);

      const response = await authAPI.registerTrial({
        username: username.trim(),
        password: password.trim(),
        telegram: telegram.trim(),
        email: email.trim() || undefined,
        hwid: currentHwid
      });

      if (response.two_factor_token) {
        setTwoFactorToken(response.two_factor_token);
      }

      if (response.requires_2fa_setup || response.needs_2fa_setup) {
        setNeeds2FASetup(true);
        setTotpSecret(response.secret || '');
        setTotpQrCode(response.qr_code || '');
        return;
      }

      onLogin(response.access_token);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      let detailStr = '';
      if (typeof detail === 'string') {
        detailStr = detail;
      } else if (Array.isArray(detail)) {
        detailStr = detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join(', ');
      } else if (detail?.msg) {
        detailStr = detail.msg;
      }
      
      setError(detailStr || 'Erro ao gerar login de teste');
    } finally {
      setLoading(false);
    }
  };

  const handleSetup2FA = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await authAPI.setup2FA({
        username: username.trim(),
        totp_code: totpCode.trim(),
        code: totpCode.trim(),
        two_factor_token: twoFactorToken
      });
      onLogin(response.access_token);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join(', '));
      } else if (detail?.msg) {
        setError(detail.msg);
      } else {
        setError('Código 2FA inválido');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2FA = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const currentHwid = generateHWID();
      setHwid(currentHwid);

      const response = await authAPI.verify2FA({
        username: username.trim(),
        totp_code: totpCode.trim(),
        code: totpCode.trim(),
        two_factor_token: twoFactorToken,
        hwid: currentHwid
      });

      if (response.needs_hwid) {
        setNeeds2FA(false);
        setNeeds2FASetup(false);
        setNeedsHwid(true);
        return;
      }

      if (response.access_token) {
        onLogin(response.access_token);
      } else {
        setError('Erro ao obter token de acesso. Tente novamente.');
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join(', '));
      } else if (detail?.msg) {
        setError(detail.msg);
      } else {
        setError('Código 2FA inválido');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleHwidActivation = async () => {
    setError('');
    setLoading(true);

    try {
      const response = await authAPI.activateHwid({
        username: username.trim(),
        password: password.trim(),
        hwid: hwid
      });
      onLogin(response.access_token);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join(', '));
      } else if (detail?.msg) {
        setError(detail.msg);
      } else {
        setError('Erro ao ativar HWID');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#030612] text-slate-100 flex items-center justify-center p-4 font-sans relative overflow-hidden">
      <div className="absolute top-4 right-4 z-50">
        <LanguageSelector />
      </div>
      
      {/* Grade de fundo cibernética */}
      <div 
        className="absolute inset-0 opacity-10 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(to right, #00f0ff 1px, transparent 1px),
            linear-gradient(to bottom, #00f0ff 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }}
      ></div>

      {/* Brilhos neon de fundo */}
      <div className="absolute top-[-10%] left-[-10%] w-[60%] h-[60%] bg-blue-500/10 rounded-full blur-[150px] pointer-events-none animate-pulse"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[60%] bg-[#00f0ff]/10 rounded-full blur-[150px] pointer-events-none animate-pulse" style={{ animationDuration: '6s' }}></div>

      <div className="max-w-md w-full relative z-10 my-auto">
        
        {/* LOGO E HEADER */}
        <div className="text-center mb-6 relative">
          <div className="relative inline-block mb-3 group cursor-pointer">
            <div className="absolute inset-[-10px] rounded-full border border-cyan-400/30 animate-ping" style={{ animationDuration: '3s' }}></div>
            <div className="absolute inset-[-6px] rounded-full border border-blue-500/30 animate-pulse"></div>
            <div className="absolute inset-0 rounded-full bg-[#00f0ff]/15 blur-xl group-hover:bg-[#00f0ff]/30 transition-all"></div>
            
            <img 
              src="/gangstar-logo.svg?v=2" 
              alt="Gangstar Remote" 
              className="relative w-20 h-20 mx-auto transition-transform duration-500 group-hover:scale-105 filter drop-shadow-[0_0_25px_rgba(0,240,255,0.7)]"
            />
          </div>
          
          <h1 className="text-2xl sm:text-3xl font-black tracking-[0.2em] text-white mb-2 uppercase font-mono relative block">
            GANGSTAR <span className="text-[#00f0ff] drop-shadow-[0_0_12px_rgba(0,240,255,0.5)]">REMOTE</span>
          </h1>

          {/* 👑 SLOGAN EXCLUSIVO: ENTRE VÁRIAS, APENAS 1 REINA GANGSTAR */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-cyan-950/80 border border-cyan-400/40 text-cyan-200 font-mono text-[11px] font-extrabold uppercase tracking-widest shadow-[0_0_20px_rgba(0,240,255,0.3)] animate-pulse">
            <Sparkles className="w-3.5 h-3.5 text-[#00f0ff] shrink-0" />
            <span>ENTRE VÁRIAS, APENAS 1 REINA: <strong className="text-white font-black">GANGSTAR</strong></span>
          </div>
        </div>

        {/* CONTAINER DO FORMULÁRIO */}
        <div className="bg-[#060b1e]/90 border border-blue-500/30 shadow-[0_0_40px_rgba(0,240,255,0.1)] rounded-2xl p-6 sm:p-8 relative overflow-hidden backdrop-blur-md">
          
          {/* Cantos cibernéticos */}
          <div className="absolute top-0 left-0 w-3 h-3 border-t-2 border-l-2 border-[#00f0ff]"></div>
          <div className="absolute top-0 right-0 w-3 h-3 border-t-2 border-r-2 border-[#00f0ff]"></div>
          <div className="absolute bottom-0 left-0 w-3 h-3 border-b-2 border-l-2 border-[#00f0ff]"></div>
          <div className="absolute bottom-0 right-0 w-3 h-3 border-b-2 border-r-2 border-[#00f0ff]"></div>

          {/* 1. FLUXO PADRÃO: LOGIN OU REGISTRO DE TESTE */}
          {!needs2FA && !needs2FASetup && !needsHwid && (
            <div>
              {/* SELETOR DE MODO: LOGIN OU TESTE GRÁTIS */}
              <div className="flex bg-[#02050f]/90 p-1 rounded-xl border border-blue-500/20 mb-5">
                <button
                  type="button"
                  onClick={() => { setIsTrialMode(false); setError(''); }}
                  className={`flex-1 py-2 text-xs font-mono font-bold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
                    !isTrialMode 
                      ? 'bg-blue-600/30 text-[#00f0ff] border border-[#00f0ff]/30 shadow-[0_0_10px_rgba(0,240,255,0.2)]' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Key className="w-3.5 h-3.5" />
                  {t('login.tab_login')}
                </button>
                <button
                  type="button"
                  onClick={() => { setIsTrialMode(true); setError(''); }}
                  className={`flex-1 py-2 text-xs font-mono font-bold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
                    isTrialMode 
                      ? 'bg-cyan-500/20 text-[#00f0ff] border border-[#00f0ff]/40 shadow-[0_0_10px_rgba(0,240,255,0.2)]' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5 text-[#00f0ff]" />
                  {t('login.tab_trial')}
                </button>
              </div>

              {/* FORMULÁRIO DE TESTE GRÁTIS (1 DIA) */}
              {isTrialMode ? (
                <form onSubmit={handleRegisterTrial} className="space-y-4">
                  <div className="bg-cyan-950/30 border border-[#00f0ff]/30 p-3 rounded-xl text-xs font-mono text-cyan-300 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-[#00f0ff] shrink-0 mt-0.5" />
                    <div>
                      <strong className="block text-[#00f0ff] font-bold">{t("login.trial_badge_title")}</strong>
                      {t("login.trial_badge_desc")}
                    </div>
                  </div>

                  {/* Usuário */}
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5 font-mono">
                      {t('login.username_desired_label')}
                    </label>
                    <div className="relative">
                      <User className="absolute left-3.5 top-3.5 h-4 w-4 text-[#00f0ff]" />
                      <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="w-full pl-11 pr-4 py-2.5 bg-[#02050f]/80 border border-blue-500/30 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-[#00f0ff] focus:ring-1 focus:ring-[#00f0ff]/40 text-sm transition-all font-mono"
                        placeholder={t("login.username_create_placeholder")}
                        required
                        minLength={3}
                      />
                    </div>
                  </div>

                  {/* Senha */}
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5 font-mono">
                      Senha <span className="text-cyan-400 font-normal">(até 8 dígitos)</span>
                    </label>

                    <div className="relative">
                      <Lock className="absolute left-3.5 top-3.5 h-4 w-4 text-[#00f0ff]" />
                      <input
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full pl-11 pr-11 py-2.5 bg-[#02050f]/80 border border-blue-500/30 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-[#00f0ff] focus:ring-1 focus:ring-[#00f0ff]/40 text-sm transition-all font-mono"
                        placeholder={t("login.password_create_placeholder")}
                        required
                        minLength={3}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-3 text-slate-500 hover:text-[#00f0ff] transition-colors focus:outline-none"
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Telegram */}
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5 font-mono">
                      Telegram <span className="text-[#00f0ff] font-bold">*</span>
                    </label>
                    <div className="relative">
                      <Send className="absolute left-3.5 top-3.5 h-4 w-4 text-[#00f0ff]" />
                      <input
                        type="text"
                        value={telegram}
                        onChange={(e) => setTelegram(e.target.value)}
                        className="w-full pl-11 pr-4 py-2.5 bg-[#02050f]/80 border border-blue-500/30 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-[#00f0ff] focus:ring-1 focus:ring-[#00f0ff]/40 text-sm transition-all font-mono"
                        placeholder={t("login.telegram_placeholder")}
                        required
                      />
                    </div>
                  </div>

                  {/* Email {t("login.email_optional")} */}
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5 font-mono">
                      E-mail <span className="text-slate-600 font-normal">{t("login.email_optional")}</span>
                    </label>
                    <div className="relative">
                      <Mail className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-500" />
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full pl-11 pr-4 py-2.5 bg-[#02050f]/80 border border-blue-500/20 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-[#00f0ff] text-sm transition-all font-mono"
                        placeholder={t("login.email_placeholder")}
                      />
                    </div>
                  </div>

                  {error && (
                    <div className="bg-red-950/30 border border-red-500/40 text-red-300 px-4 py-3 rounded-xl text-xs font-mono leading-relaxed">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-3 bg-gradient-to-r from-blue-700 via-blue-600 to-[#00f0ff] hover:brightness-110 disabled:opacity-50 text-white font-bold rounded-xl transition-all flex items-center justify-center gap-2 text-xs uppercase tracking-widest font-mono border border-blue-400/20 active:scale-[0.98] shadow-[0_0_20px_rgba(0,240,255,0.25)]"
                  >
                    {loading ? (
                      <>
                        <Loader className="w-4 h-4 animate-spin text-white" />
                        {t("login.btn_generating_trial")}
                      </>
                    ) : (
                      <>
                        <Zap className="w-4 h-4 text-[#00f0ff] fill-[#00f0ff]" />
                        {t("login.btn_trial")}
                      </>
                    )}
                  </button>
                </form>
              ) : (
                /* FORMULÁRIO PADRÃO DE LOGIN */
                <form onSubmit={handleSubmit} className="space-y-5">
                  {/* Usuário */}
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 font-mono">
                      {t("login.username_label")}
                    </label>
                    <div className="relative">
                      <User className="absolute left-3.5 top-3.5 h-4 w-4 text-[#00f0ff]" />
                      <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="w-full pl-11 pr-4 py-3 bg-[#02050f]/80 border border-blue-500/20 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-[#00f0ff] focus:ring-1 focus:ring-[#00f0ff]/30 text-sm transition-all font-mono"
                        placeholder={t("login.username_placeholder")}
                        required
                      />
                    </div>
                  </div>

                  {/* Senha */}
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 font-mono">
                      {t("login.password_label")}
                    </label>
                    <div className="relative">
                      <Lock className="absolute left-3.5 top-3.5 h-4 w-4 text-[#00f0ff]" />
                      <input
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full pl-11 pr-11 py-3 bg-[#02050f]/80 border border-blue-500/20 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-[#00f0ff] focus:ring-1 focus:ring-[#00f0ff]/30 text-sm transition-all font-mono"
                        placeholder={t("login.password_placeholder")}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-3.5 text-slate-500 hover:text-[#00f0ff] transition-colors focus:outline-none"
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {error && (
                    <div className="bg-red-950/20 border border-red-500/40 text-red-400 px-4 py-3 rounded-xl text-xs font-mono">
                      ⚠️ {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-3 bg-gradient-to-r from-blue-700 via-blue-600 to-[#00f0ff] hover:brightness-110 disabled:from-slate-800 disabled:to-slate-900 disabled:text-slate-650 disabled:opacity-50 text-white font-bold rounded-xl transition-all flex items-center justify-center gap-2 text-xs uppercase tracking-widest font-mono border border-blue-400/20 active:scale-[0.98]"
                  >
                    {loading ? (
                      <>
                        <Loader className="w-4 h-4 animate-spin text-white" />
                        {t("login.btn_verifying")}
                      </>
                    ) : (
                      <span>{t("login.btn_login")}</span>
                    )}
                  </button>
                </form>
              )}
            </div>
          )}

          {/* 2. FLUXO 2FA: CONFIGURAÇÃO INICIAL GOOGLE AUTHENTICATOR (QR CODE) */}
          {needs2FASetup && (
            <div>
              <div className="text-center mb-4">
                <div className="inline-flex items-center justify-center w-12 h-12 bg-cyan-950/40 border border-[#00f0ff]/40 rounded-full mb-2 text-[#00f0ff] shadow-[0_0_15px_rgba(0,240,255,0.25)]">
                  <QrCode className="w-6 h-6" />
                </div>
                <h2 className="text-sm font-black text-white uppercase tracking-wider font-mono">
                  {t("login.totp_setup_title")}
                </h2>
                <p className="text-slate-400 text-xs mt-1 leading-relaxed">
                  {t("login.totp_setup_desc")}
                </p>
              </div>

              <div className="space-y-4">
                {/* QR Code */}
                {totpQrCode && (
                  <div className="flex justify-center my-2">
                    <div className="p-3 bg-white rounded-2xl shadow-[0_0_25px_rgba(0,240,255,0.2)] border-2 border-[#00f0ff]/40">
                      <img 
                        src={totpQrCode} 
                        alt="QR Code Google Authenticator" 
                        className="w-44 h-44 object-contain rounded-lg"
                      />
                    </div>
                  </div>
                )}

                {/* Chave manual */}
                {totpSecret && (
                  <div className="bg-[#02050f]/80 border border-blue-500/20 rounded-xl p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider font-mono">
                        {t("login.totp_key_label")}
                      </span>
                      <button
                        type="button"
                        onClick={handleCopySecret}
                        className="text-[10px] text-[#00f0ff] hover:text-white flex items-center gap-1 font-mono transition-colors"
                      >
                        {copiedSecret ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        {copiedSecret ? t("login.totp_copied") : t("login.totp_copy")}
                      </button>
                    </div>
                    <div className="font-mono text-xs text-[#00f0ff] break-all select-all tracking-wider bg-black/40 p-2 rounded border border-[#00f0ff]/10 text-center">
                      {totpSecret}
                    </div>
                  </div>
                )}

                {/* Formulário de confirmação do código */}
                <form onSubmit={handleSetup2FA} className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1 font-mono text-center">
                      {t("login.totp_code_label")}
                    </label>
                    <input
                      type="text"
                      maxLength={6}
                      value={totpCode}
                      onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                      placeholder="000000"
                      autoFocus
                      className="w-full py-3 bg-[#02050f]/80 border border-blue-500/30 rounded-xl text-center text-2xl font-black tracking-[0.35em] text-[#00f0ff] placeholder-slate-700 focus:outline-none focus:border-[#00f0ff] focus:ring-1 focus:ring-[#00f0ff]/40 font-mono transition-all"
                      required
                    />
                  </div>

                  {error && (
                    <div className="bg-red-950/20 border border-red-500/40 text-red-400 px-4 py-2.5 rounded-xl text-xs font-mono">
                      ⚠️ {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading || totpCode.length < 6}
                    className="w-full py-3 bg-gradient-to-r from-emerald-600 to-teal-500 hover:brightness-110 disabled:opacity-50 text-white font-bold rounded-xl transition-all flex items-center justify-center gap-2 text-xs uppercase tracking-widest font-mono border border-emerald-400/20"
                  >
                    {loading ? (
                      <>
                        <Loader className="w-4 h-4 animate-spin text-white" />
                        {t("login.totp_validating")}
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="w-4 h-4" />
                        {t("login.totp_confirm_btn")}
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={resetAll2FAStates}
                    className="w-full py-2 text-slate-400 hover:text-white text-xs font-mono flex items-center justify-center gap-1 transition-colors"
                  >
                    <ArrowLeft className="w-3 h-3" />
                    {t("login.totp_back")}
                  </button>
                </form>
              </div>
            </div>
            )}

            {/* 3. FLUXO 2FA: VERIFICAÇÃO GOOGLE AUTHENTICATOR (CÓDIGO 6 DÍGITOS) */}
            {needs2FA && !needs2FASetup && (
              <div>
                <div className="text-center mb-6">
                  <div className="inline-flex items-center justify-center w-14 h-14 bg-cyan-950/40 border border-[#00f0ff]/40 rounded-full mb-3 text-[#00f0ff] shadow-[0_0_20px_rgba(0,240,255,0.3)]">
                    <ShieldCheck className="w-7 h-7" />
                  </div>
                  <h2 className="text-base font-black text-white uppercase tracking-wider font-mono">
                    {t("login.totp_verify_title")}
                  </h2>
                  <p className="text-slate-400 text-xs mt-2 leading-relaxed">
                    {t("login.totp_verify_desc")}
                  </p>
                </div>

                <form onSubmit={handleVerify2FA} className="space-y-5">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 font-mono text-center">
                      Código de Segurança (TOTP)
                    </label>
                    <input
                      type="text"
                      maxLength={6}
                      value={totpCode}
                      onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                      placeholder="000000"
                      autoFocus
                      className="w-full py-3.5 bg-[#02050f]/80 border border-blue-500/30 rounded-xl text-center text-3xl font-black tracking-[0.35em] text-[#00f0ff] placeholder-slate-700 focus:outline-none focus:border-[#00f0ff] focus:ring-1 focus:ring-[#00f0ff]/40 font-mono transition-all"
                      required
                    />
                  </div>

                  {error && (
                    <div className="bg-red-950/20 border border-red-500/40 text-red-400 px-4 py-3 rounded-xl text-xs font-mono">
                      ⚠️ {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading || totpCode.length < 6}
                    className="w-full py-3 bg-gradient-to-r from-blue-700 via-blue-600 to-[#00f0ff] hover:brightness-110 disabled:opacity-50 text-white font-bold rounded-xl transition-all flex items-center justify-center gap-2 text-xs uppercase tracking-widest font-mono border border-blue-400/20 active:scale-[0.98]"
                  >
                    {loading ? (
                      <>
                        <Loader className="w-4 h-4 animate-spin text-white" />
                        <span>Verificando 2FA...</span>
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="w-4 h-4" />
                        {t("login.totp_verify_btn")}
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={resetAll2FAStates}
                    className="w-full py-2 text-slate-400 hover:text-white text-xs font-mono flex items-center justify-center gap-1 transition-colors"
                  >
                    <ArrowLeft className="w-3 h-3" />
                    {t("login.totp_back")}
                  </button>
                </form>
              </div>
            )}

            {/* 4. FLUXO HWID: VINCULAR DISPOSITIVO */}
            {needsHwid && (
              <div>
                <div className="text-center mb-6">
                  <div className="inline-flex items-center justify-center w-12 h-12 bg-cyan-950/40 border border-[#00f0ff]/40 rounded-full mb-3 text-[#00f0ff]">
                    <Key className="w-5 h-5" />
                  </div>
                  <h2 className="text-sm font-black text-white uppercase tracking-wider font-mono">{t("login.hwid_title")}</h2>
                  <p className="text-slate-400 text-xs mt-2 leading-relaxed">
                    {t("login.hwid_desc")}
                  </p>
                </div>

                <div className="space-y-5">
                  <div className="bg-[#02050f]/80 border border-blue-500/20 rounded-xl p-4">
                    <label className="block text-[9px] font-bold text-slate-400 uppercase tracking-wider font-mono mb-2">
                      {t("login.hwid_code_label")}
                    </label>
                    <div className="bg-[#030612] rounded-lg p-3 font-mono text-[11px] text-[#00f0ff] break-all select-all border border-[#00f0ff]/10">
                      {hwid}
                    </div>
                  </div>

                  {error && (
                    <div className="bg-red-950/20 border border-red-500/40 text-red-400 px-4 py-3 rounded-xl text-xs font-mono">
                      ⚠️ {error}
                    </div>
                  )}

                  <button
                    onClick={handleHwidActivation}
                    disabled={loading}
                    className="w-full py-3 bg-gradient-to-r from-emerald-600 to-teal-500 hover:brightness-110 text-white font-bold rounded-xl transition-all disabled:opacity-50 flex items-center justify-center gap-2 text-xs uppercase tracking-widest font-mono border border-emerald-400/20"
                  >
                    {loading ? t('login.hwid_registering') : '✅ ' + t('login.hwid_register_btn')}
                  </button>

                  <button
                    onClick={resetAll2FAStates}
                    className="w-full bg-[#050b1d] hover:bg-[#0c1432] text-slate-400 hover:text-white border border-blue-500/20 font-bold py-2.5 rounded-xl transition-all text-xs uppercase tracking-wider font-mono"
                  >
                    Voltar
                  </button>
                </div>
              </div>
            )}
        </div>
      </div>
    </div>
  );
}
