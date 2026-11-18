import type { MouseEvent } from 'react';
import type { Cliente } from '@/types/dashboard';
import DeviceRow from './DeviceRow';
import { Smartphone, Zap } from 'lucide-react';
import { useTranslation } from '../../utils/i18n';

interface DeviceTableProps {
  clientes: Cliente[];
  loading: boolean;
  onRowClick: (cliente: Cliente) => void;
  onRowContextMenu: (event: MouseEvent, cliente: Cliente) => void;
  onDeleteDevice?: (cliente: Cliente) => void;
  onCreateApk?: () => void;
  onOpenVnc?: (cliente: Cliente) => void;
  onTogglePin?: (deviceId: string) => void;
}

export default function DeviceTable({
  clientes,
  loading,
  onRowClick,
  onRowContextMenu,
  onDeleteDevice,
  onCreateApk,
  onOpenVnc,
  onTogglePin,
}: DeviceTableProps) {
  const { t } = useTranslation();

  if (loading && clientes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-cyan-300 bg-[#06102b]/60 rounded-3xl border border-blue-500/30 backdrop-blur-xl">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cyan-400 mb-4 shadow-[0_0_15px_rgba(6,182,212,0.5)]" />
        <p className="font-mono text-xs uppercase tracking-widest text-cyan-300 font-bold">{t('table.loading')}</p>
      </div>
    );
  }

  if (clientes.length === 0) {
    return (
      <div className="bg-[#081535]/80 backdrop-blur-2xl rounded-3xl border border-blue-500/30 p-12 text-center shadow-[0_10px_35px_rgba(2,132,199,0.15)] relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent"></div>
        <Smartphone className="w-16 h-16 mx-auto stroke-1 text-cyan-400/40 mb-4 animate-pulse" />
        <p className="text-cyan-200 font-black text-lg mb-1 uppercase font-mono tracking-wider">{t('table.no_devices')}</p>
        <p className="text-blue-300/60 text-xs mb-6 max-w-md mx-auto font-mono">
          {t('table.no_devices_sub')}
        </p>
        {onCreateApk && (
          <button
            type="button"
            onClick={onCreateApk}
            className="px-6 py-3 bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white rounded-xl text-xs font-black uppercase font-mono tracking-wider shadow-lg shadow-cyan-500/25 border border-cyan-300/40 transition-all cursor-pointer active:scale-95 inline-flex items-center gap-2"
          >
            <Zap className="w-4 h-4 text-cyan-200" />
            <span>{t('table.gen_apk')}</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-cyan-500/35 bg-gradient-to-b from-[#061229]/95 via-[#030a1a]/95 to-[#01040f]/95 backdrop-blur-3xl p-5 shadow-[0_25px_70px_rgba(0,0,0,0.95)] relative overflow-hidden transition-all">
      {/* Top glowing laser beam */}
      <div className="absolute top-0 left-0 right-0 h-[3.5px] bg-gradient-to-r from-blue-600 via-cyan-400 via-sky-400 to-blue-600 shadow-[0_0_25px_rgba(6,182,212,1)]"></div>

      {/* Header Info Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-3 mb-3 bg-[#040b1e]/90 rounded-2xl border border-cyan-500/25 shadow-inner gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 rounded-xl bg-cyan-500/20 border border-cyan-400/50 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.3)] shrink-0">
            <Smartphone className="w-4 h-4 text-cyan-300 animate-pulse" />
          </div>
          <div className="min-w-0">
            <span className="text-xs font-black text-white font-mono uppercase tracking-widest block truncate">Painel de Dispositivos</span>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono font-bold shrink-0">
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 shadow-[0_0_10px_rgba(6,182,212,0.25)] whitespace-nowrap">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
            {clientes.filter(c => c.status === 'online').length} ONLINE
          </span>
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-800 text-slate-400 whitespace-nowrap">
            <span className="w-2 h-2 rounded-full bg-slate-600"></span>
            {clientes.filter(c => c.status === 'offline').length} OFFLINE
          </span>
        </div>
      </div>
      
      <div className="w-full overflow-x-auto">
        <table className="w-full text-left border-separate border-spacing-y-2.5">
          <thead>
            <tr className="text-cyan-300/80 font-mono text-[10px] uppercase font-black tracking-wider">
              <th className="px-3 py-2 font-black w-[100px]">{t('table.status')}</th>
              <th className="px-3 py-2 font-black">{t('table.model')}</th>
              <th className="px-3 py-2 font-black">{t('table.activity')}</th>
              <th className="px-3 py-2 font-black">{t('table.ip')}</th>
              <th className="px-3 py-2 font-black">{t('table.system')}</th>
              <th className="px-3 py-2 font-black text-right w-[180px]">AÇÕES</th>
            </tr>
          </thead>
          <tbody>
            {clientes.map((cliente) => (
              <DeviceRow
                key={cliente.deviceId}
                cliente={cliente}
                onClick={() => onRowClick(cliente)}
                onContextMenu={(e: MouseEvent) => onRowContextMenu(e, cliente)}
                onDeleteDevice={onDeleteDevice}
                onOpenVnc={onOpenVnc}
                onTogglePin={onTogglePin}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
