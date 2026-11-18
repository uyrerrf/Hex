import { useState, useEffect } from 'react';
import { adminAPI, devicesAPI } from '../services/api';
import { 
  Shield, Users, UserPlus, Trash2, Ban, RefreshCw, 
  Edit, Check, LogOut, Smartphone, Search,
  User, ShieldCheck
} from 'lucide-react';

interface User {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  is_banned: boolean;
  hwid: string | null;
  hwid_activated_at: string | null;
  totp_enabled: boolean;
  created_at: string;
  expires_at: string | null;
  last_login: string | null;
  last_ip: string | null;
  notes: string | null;
  device_count: number;
}

interface DeviceAdmin {
  id: number;
  device_id: string;
  model: string | null;
  manufacturer: string | null;
  android_version: string | null;
  last_seen: string | null;
  is_online: boolean;
  owner_id: number | null;
  owner_username: string | null;
}

interface Stats {
  total_users: number;
  active_users: number;
  banned_users: number;
  total_devices: number;
  online_devices: number;
}

interface AdminPanelProps {
  onLogout: () => void;
}

export default function AdminPanel({ onLogout }: AdminPanelProps) {
  const [activeTab, setActiveTab] = useState<'users' | 'devices'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [devices, setDevices] = useState<DeviceAdmin[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  
  // Modal de criar usuário
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', is_admin: false, expiration_days: 0, notes: '' });
  
  // Modal de editar usuário
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({ email: '', password: '', notes: '', is_admin: false, expiration_days: 0, clear_expiration: false });

  // Carregar dados
  useEffect(() => {
    loadData();
    
    // Auto-refresh a cada 5 segundos (com pausa em aba oculta)
    const interval = setInterval(() => {
      if (!document.hidden) loadData();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [usersData, statsData, devicesData] = await Promise.all([
        adminAPI.getUsers(),
        adminAPI.getStats(),
        adminAPI.getDevices()
      ]);
      setUsers(usersData);
      setStats(statsData);
      setDevices(devicesData);
      setLoading(false);
    } catch (err: any) {
      if (!loading) return;
      setError(err.response?.data?.detail || 'Erro ao carregar dados');
      setLoading(false);
    }
  };

  const handleCreateUser = async () => {
    try {
      await adminAPI.createUser(newUser);
      setShowCreateModal(false);
      setNewUser({ username: '', email: '', password: '', is_admin: false, expiration_days: 0, notes: '' });
      setSuccess('Usuário criado com sucesso!');
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao criar usuário');
    }
  };

  const handleUpdateUser = async () => {
    if (!editingUser) return;
    try {
      const updateData: any = {};
      if (editForm.email) updateData.email = editForm.email;
      if (editForm.password) updateData.password = editForm.password;
      if (editForm.notes !== editingUser.notes) updateData.notes = editForm.notes;
      if (editForm.is_admin !== editingUser.is_admin) updateData.is_admin = editForm.is_admin;
      if (editForm.clear_expiration) updateData.clear_expiration = true;
      else if (editForm.expiration_days > 0) updateData.expiration_days = editForm.expiration_days;
      
      await adminAPI.updateUser(editingUser.id, updateData);
      setEditingUser(null);
      setSuccess('Usuário atualizado!');
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao atualizar usuário');
    }
  };

  const handleBanUser = async (userId: number, isBanned: boolean) => {
    try {
      if (isBanned) {
        await adminAPI.unbanUser(userId);
        setSuccess('Usuário desbanido!');
      } else {
        await adminAPI.banUser(userId);
        setSuccess('Usuário banido!');
      }
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao banir/desbanir usuário');
    }
  };

  const handleDeleteUser = async (userId: number) => {
    if (!confirm('Tem certeza que deseja excluir este usuário?')) return;
    try {
      await adminAPI.deleteUser(userId);
      setSuccess('Usuário excluído!');
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao excluir usuário');
    }
  };

  const handleResetHwid = async (userId: number) => {
    if (!confirm('Resetar HWID deste usuário?')) return;
    try {
      await adminAPI.resetHwid(userId);
      setSuccess('HWID resetado!');
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao resetar HWID');
    }
  };

  const handleReset2FA = async (userId: number) => {
    if (!confirm('Deseja resetar o Google Authenticator (2FA) deste usuário? Ele precisará ler o novo QR Code no próximo login.')) return;
    try {
      await adminAPI.reset2FA(userId);
      setSuccess('2FA do Google Authenticator resetado com sucesso!');
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao resetar 2FA');
    }
  };

  const safeUsers = Array.isArray(users) ? users : [];
  const safeDevices = Array.isArray(devices) ? devices : [];

  const filteredUsers = safeUsers.filter(u => 
    (u?.username || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (u?.email || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredDevices = safeDevices.filter(d =>
    (d?.device_id || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (d?.model?.toLowerCase() || '').includes(searchTerm.toLowerCase()) ||
    (d?.owner_username?.toLowerCase() || '').includes(searchTerm.toLowerCase())
  );

  const onlineDevices = safeDevices.filter(d => d?.is_online);

  const currentStats = stats || {
    total_users: safeUsers.length,
    active_users: safeUsers.filter(u => u.is_active && !u.is_banned).length,
    banned_users: safeUsers.filter(u => u.is_banned).length,
    total_devices: safeDevices.length,
    online_devices: onlineDevices.length
  };

  // Auto-hide messages
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(''), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(''), 3000);
      return () => clearTimeout(timer);
    }
  }, [success]);

  if (loading) {
    return (
      <div className="relative z-10 min-h-screen bg-[#070c1e]/95 backdrop-blur-md flex items-center justify-center">
        <div className="text-white text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-500 mx-auto mb-4"></div>
          <p className="font-semibold text-lg">Carregando painel admin...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative z-10 min-h-screen bg-[#070c1e]/95 backdrop-blur-md text-white">
      {/* Header */}
      <header className="bg-black/60 border-b border-red-500/30 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-red-600 rounded-lg shadow-lg shadow-red-500/30">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-wide">Admin Panel</h1>
              <p className="text-xs text-red-400 font-mono">Gerenciamento de Operadores e Dispositivos</p>
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={onLogout}
              className="flex items-center space-x-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span>Sair</span>
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Estatísticas */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className="bg-[#111c44]/80 backdrop-blur-md rounded-lg p-4 border border-blue-500/20 shadow-lg">
            <div className="flex items-center space-x-3">
              <Users className="w-8 h-8 text-blue-400" />
              <div>
                <p className="text-2xl font-bold text-white">{currentStats.total_users}</p>
                <p className="text-xs text-gray-400">Total Usuários</p>
              </div>
            </div>
          </div>
          <div className="bg-[#111c44]/80 backdrop-blur-md rounded-lg p-4 border border-green-500/30 shadow-lg">
            <div className="flex items-center space-x-3">
              <Check className="w-8 h-8 text-green-400" />
              <div>
                <p className="text-2xl font-bold text-white">{currentStats.active_users}</p>
                <p className="text-xs text-gray-400">Ativos</p>
              </div>
            </div>
          </div>
          <div className="bg-[#111c44]/80 backdrop-blur-md rounded-lg p-4 border border-red-500/30 shadow-lg">
            <div className="flex items-center space-x-3">
              <Ban className="w-8 h-8 text-red-400" />
              <div>
                <p className="text-2xl font-bold text-white">{currentStats.banned_users}</p>
                <p className="text-xs text-gray-400">Banidos</p>
              </div>
            </div>
          </div>
          <div className="bg-[#111c44]/80 backdrop-blur-md rounded-lg p-4 border border-blue-500/30 shadow-lg">
            <div className="flex items-center space-x-3">
              <Smartphone className="w-8 h-8 text-blue-400" />
              <div>
                <p className="text-2xl font-bold text-white">{currentStats.total_devices}</p>
                <p className="text-xs text-gray-400">Dispositivos</p>
              </div>
            </div>
          </div>
          <div className="bg-[#111c44]/80 backdrop-blur-md rounded-lg p-4 border border-green-500/30 shadow-lg">
            <div className="flex items-center space-x-3">
              <Smartphone className="w-8 h-8 text-green-400" />
              <div>
                <p className="text-2xl font-bold text-white">{currentStats.online_devices}</p>
                <p className="text-xs text-gray-400">Dispositivos Online</p>
              </div>
            </div>
          </div>
        </div>

        {/* Mensagens */}
        {error && (
          <div className="bg-red-500/10 border border-red-500 text-red-400 px-4 py-3 rounded-lg mb-4 flex justify-between">
            <span>{error}</span>
            <button onClick={() => setError('')}>×</button>
          </div>
        )}
        {success && (
          <div className="bg-green-500/10 border border-green-500 text-green-400 px-4 py-3 rounded-lg mb-4">
            ✅ {success}
          </div>
        )}

        {/* Tabs */}
        <div className="flex space-x-2 mb-4">
          <button
            onClick={() => setActiveTab('users')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors ${
              activeTab === 'users' 
                ? 'bg-red-600 text-white' 
                : 'bg-slate-700 text-gray-300 hover:bg-slate-600'
            }`}
          >
            <Users className="w-4 h-4" />
            <span>Usuários ({users.length})</span>
          </button>
          <button
            onClick={() => setActiveTab('devices')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors ${
              activeTab === 'devices' 
                ? 'bg-red-600 text-white' 
                : 'bg-slate-700 text-gray-300 hover:bg-slate-600'
            }`}
          >
            <Smartphone className="w-4 h-4" />
            <span>Dispositivos ({devices.length})</span>
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder={activeTab === 'users' ? "Buscar usuário..." : "Buscar dispositivo..."}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 pr-4 py-2 bg-[#111c44] border border-blue-500/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-600 w-64"
            />
          </div>
          <div className="flex space-x-2">
            <button
              onClick={loadData}
              className="flex items-center space-x-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Atualizar</span>
            </button>
            {activeTab === 'users' && (
              <button
                onClick={() => setShowCreateModal(true)}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors"
              >
                <UserPlus className="w-4 h-4" />
                <span>Novo Usuário</span>
              </button>
            )}
          </div>
        </div>

        {/* Conteúdo - Usuários */}
        {activeTab === 'users' && (
          <div className="bg-[#111c44]/50 rounded-lg border border-blue-500/20 overflow-hidden">
            <table className="w-full">
              <thead className="bg-[#0b1329]/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Usuário</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">HWID</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">2FA (Google)</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Dispositivos</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Último Acesso</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                      <Users className="w-12 h-12 mx-auto mb-3 text-slate-500/50" />
                      <p className="text-base font-semibold">Nenhum usuário cadastrado ou encontrado</p>
                      <p className="text-xs text-gray-500 mt-1">Clique em "Novo Usuário" para cadastrar um operador ou clique em Atualizar</p>
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-700/30">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-semibold text-white flex items-center">
                          {user.username}
                          {user.is_admin && (
                            <span className="ml-2 px-2 py-0.5 bg-red-600 text-white text-xs rounded">ADMIN</span>
                          )}
                        </p>
                        <p className="text-xs text-gray-400">{user.email}</p>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {user.is_banned ? (
                        <span className="px-2 py-1 bg-red-500/20 text-red-400 text-xs rounded-full">🚫 Banido</span>
                      ) : user.is_active ? (
                        <div className="flex flex-col gap-1">
                          <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded-full w-fit">✅ Ativo</span>
                          {user.expires_at ? (
                            new Date(user.expires_at) < new Date() ? (
                              <span className="px-2 py-0.5 bg-red-600/30 text-red-300 text-[10px] font-bold rounded-full w-fit">🔴 EXPIRADO ({new Date(user.expires_at).toLocaleDateString('pt-BR')})</span>
                            ) : (
                              <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-300 text-[10px] rounded-full w-fit">⏳ Expira em {new Date(user.expires_at).toLocaleDateString('pt-BR')}</span>
                            )
                          ) : (
                            <span className="text-[10px] text-gray-500 italic">Sem expiração</span>
                          )}
                        </div>
                      ) : (
                        <span className="px-2 py-1 bg-gray-500/20 text-gray-400 text-xs rounded-full">⏸️ Inativo</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {user.hwid ? (
                        <div className="flex items-center space-x-2">
                          <span className="text-xs font-mono text-green-400 bg-green-500/10 px-2 py-1 rounded">
                            {user.hwid.substring(0, 12)}...
                          </span>
                          <button
                            onClick={() => handleResetHwid(user.id)}
                            className="p-1 text-yellow-400 hover:bg-yellow-500/20 rounded"
                            title="Resetar HWID"
                          >
                            <RefreshCw className="w-3 h-3" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-500">Não ativado</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {user.totp_enabled ? (
                        <div className="flex items-center space-x-1.5">
                          <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <ShieldCheck className="w-3 h-3 text-emerald-400" />
                            <span>Ativo</span>
                          </span>
                          <button
                            onClick={() => handleReset2FA(user.id)}
                            className="p-1 text-yellow-400 hover:bg-yellow-500/20 rounded transition-colors"
                            title="Resetar Google Authenticator (2FA)"
                          >
                            <RefreshCw className="w-3 h-3" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400 bg-slate-800/80 border border-slate-700 px-2 py-0.5 rounded-full">Pendente</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-white font-semibold">{user.device_count}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div>
                        <p className="text-xs text-gray-300">
                          {user.last_login ? new Date(user.last_login).toLocaleString() : 'Nunca'}
                        </p>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end space-x-1">
                        <button
                          onClick={() => {
                            setEditingUser(user);
                            setEditForm({
                              email: user.email,
                              password: '',
                              notes: user.notes || '',
                              is_admin: user.is_admin,
                              expiration_days: 0,
                              clear_expiration: false
                            });
                          }}
                          className="p-2 text-blue-400 hover:bg-blue-500/20 rounded"
                          title="Editar"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleBanUser(user.id, user.is_banned)}
                          className={`p-2 rounded ${user.is_banned ? 'text-green-400 hover:bg-green-500/20' : 'text-yellow-400 hover:bg-yellow-500/20'}`}
                          title={user.is_banned ? 'Desbanir' : 'Banir'}
                        >
                          <Ban className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteUser(user.id)}
                          className="p-2 text-red-400 hover:bg-red-500/20 rounded"
                          title="Excluir"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )))}
              </tbody>
            </table>
          </div>
        )}

        {/* Conteúdo - Dispositivos */}
        {activeTab === 'devices' && (
          <div className="bg-[#111c44]/50 rounded-lg border border-blue-500/20 overflow-hidden">
            <table className="w-full">
              <thead className="bg-[#0b1329]/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Dispositivo</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Operador</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Último Acesso</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {filteredDevices.map((device) => (
                  <tr key={device.id} className="hover:bg-slate-700/30">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-semibold text-white">{device.model || 'Desconhecido'}</p>
                        <p className="text-xs text-gray-400">{device.device_id.substring(0, 16)}...</p>
                        <p className="text-xs text-gray-500">{device.manufacturer} • Android {device.android_version}</p>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {device.is_online ? (
                        <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded-full flex items-center w-fit">
                          <span className="w-2 h-2 bg-green-400 rounded-full mr-2 animate-pulse"></span>
                          Online
                        </span>
                      ) : (
                        <span className="px-2 py-1 bg-gray-500/20 text-gray-400 text-xs rounded-full">Offline</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {device.owner_username ? (
                        <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded flex items-center w-fit">
                          <User className="w-3 h-3 mr-1" />
                          {device.owner_username}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-500 italic">Não atribuído</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-xs text-gray-300">
                        {device.last_seen ? new Date(device.last_seen).toLocaleString() : 'Nunca'}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        <button
                          onClick={async () => {
                            if (confirm(`Deseja realmente excluir o dispositivo "${device.model || device.device_id}"?`)) {
                              try {
                                await devicesAPI.deleteDevice(device.device_id);
                                setSuccess("Dispositivo excluído!");
                                loadData();
                              } catch (err: any) {
                                setError(err.response?.data?.detail || "Erro ao excluir dispositivo");
                              }
                            }
                          }}
                          className="flex items-center space-x-1 px-3 py-1.5 bg-red-600/80 hover:bg-red-700 text-white text-xs rounded transition-colors"
                          title="Excluir dispositivo"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Excluir</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Criar Usuário */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#111c44] rounded-lg p-6 w-full max-w-md mx-4">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center">
              <UserPlus className="w-5 h-5 mr-2 text-green-400" />
              Criar Novo Usuário
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Usuário</label>
                <input
                  type="text"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                  placeholder="nome_usuario"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">E-mail</label>
                <input
                  type="email"
                  value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                  placeholder="email@exemplo.com"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Senha</label>
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                  placeholder="********"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Validade do Login (Expiração)</label>
                <select
                  value={newUser.expiration_days}
                  onChange={(e) => setNewUser({ ...newUser, expiration_days: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                >
                  <option value={0}>Sem expiração (Vitalício)</option>
                  <option value={1}>1 Dia</option>
                  <option value={7}>7 Dias</option>
                  <option value={15}>15 Dias</option>
                  <option value={30}>30 Dias</option>
                  <option value={60}>60 Dias</option>
                  <option value={90}>90 Dias</option>
                  <option value={365}>1 Ano</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Notas</label>
                <textarea
                  value={newUser.notes}
                  onChange={(e) => setNewUser({ ...newUser, notes: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                  rows={2}
                />
              </div>
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_admin"
                  checked={newUser.is_admin}
                  onChange={(e) => setNewUser({ ...newUser, is_admin: e.target.checked })}
                  className="mr-2"
                />
                <label htmlFor="is_admin" className="text-sm text-gray-300">É administrador</label>
              </div>
            </div>
            <div className="flex space-x-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                className="flex-1 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded"
              >
                Cancelar
              </button>
              <button
                onClick={handleCreateUser}
                className="flex-1 py-2 bg-green-600 hover:bg-green-700 text-white rounded"
              >
                Criar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Editar Usuário */}
      {editingUser && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#111c44] rounded-lg p-6 w-full max-w-md mx-4">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center">
              <Edit className="w-5 h-5 mr-2 text-blue-400" />
              Editar: {editingUser.username}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">E-mail</label>
                <input
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Nova Senha</label>
                <input
                  type="password"
                  value={editForm.password}
                  onChange={(e) => setEditForm({ ...editForm, password: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                  placeholder="Deixe vazio para manter"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Adicionar / Alterar Tempo de Expiração</label>
                <select
                  value={editForm.expiration_days}
                  onChange={(e) => setEditForm({ ...editForm, expiration_days: parseInt(e.target.value), clear_expiration: false })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white mb-2"
                >
                  <option value={0}>Manter expiração atual</option>
                  <option value={1}>Mais 1 Dia (a partir de hoje)</option>
                  <option value={7}>Mais 7 Dias (a partir de hoje)</option>
                  <option value={15}>Mais 15 Dias (a partir de hoje)</option>
                  <option value={30}>Mais 30 Dias (a partir de hoje)</option>
                  <option value={60}>Mais 60 Dias (a partir de hoje)</option>
                  <option value={90}>Mais 90 Dias (a partir de hoje)</option>
                  <option value={365}>Mais 1 Ano (a partir de hoje)</option>
                </select>
                {editingUser?.expires_at && (
                  <div className="flex items-center mt-1">
                    <input
                      type="checkbox"
                      id="clear_exp"
                      checked={editForm.clear_expiration}
                      onChange={(e) => setEditForm({ ...editForm, clear_expiration: e.target.checked, expiration_days: 0 })}
                      className="mr-2"
                    />
                    <label htmlFor="clear_exp" className="text-xs text-yellow-300">Remover expiração (Tornar sem limite)</label>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Notas</label>
                <textarea
                  value={editForm.notes}
                  onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-blue-500/25 rounded text-white"
                  rows={2}
                />
              </div>
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="edit_is_admin"
                  checked={editForm.is_admin}
                  onChange={(e) => setEditForm({ ...editForm, is_admin: e.target.checked })}
                  className="mr-2"
                />
                <label htmlFor="edit_is_admin" className="text-sm text-gray-300">É administrador</label>
              </div>
            </div>
            <div className="flex space-x-3 mt-6">
              <button
                onClick={() => setEditingUser(null)}
                className="flex-1 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded"
              >
                Cancelar
              </button>
              <button
                onClick={handleUpdateUser}
                className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded"
              >
                Salvar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}