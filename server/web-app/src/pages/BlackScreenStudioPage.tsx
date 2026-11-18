import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import BlackScreenEditor from '../components/BlackScreenEditor';
import type { BlackScreenTemplate } from '../components/BlackScreenEditor';

export default function BlackScreenStudioPage() {
  const navigate = useNavigate();
  const [editingTemplate] = useState<BlackScreenTemplate | undefined>(undefined);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  return (
    <div className="min-h-screen bg-[#020714] text-slate-100 relative overflow-hidden font-mono">
      {/* Toast Feedback Notification */}
      {toastMessage && (
        <div className="fixed top-6 right-6 z-[999999] bg-[#091838] border-2 border-cyan-400 text-cyan-100 px-5 py-3 rounded-2xl shadow-[0_0_30px_rgba(6,182,212,0.6)] font-mono text-xs font-bold flex items-center gap-2.5 animate-in slide-in-from-top duration-300">
          <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Editor Completo de Telas Pretas & Injects */}
      <BlackScreenEditor
        isOpen={true}
        onClose={() => navigate('/dashboard')}
        onSave={(template) => {
          showToast(`✨ Template "${template.name}" salvo com sucesso!`);
        }}
        onApply={(template) => {
          showToast(`⚡ Template "${template.name}" pronto para injeção em dispositivos!`);
        }}
        initialTemplate={editingTemplate}
      />
    </div>
  );
}
