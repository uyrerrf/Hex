import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Zap } from 'lucide-react';

export default function APKBypassIframePage() {
  const navigate = useNavigate();
  // IP da rede local / porta do novo bypass
  const bypassUrl = `http://${window.location.hostname}:8088/login`;

  return (
    <div className="h-screen w-screen bg-[#070b19] text-white flex flex-col overflow-hidden">
      {/* Header Superior com controles e botão Voltar */}
      <div className="bg-[#0b1329]/95 border-b border-cyan-500/25 px-4 py-2.5 flex items-center justify-between shadow-lg backdrop-blur-md z-10 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/80 hover:bg-slate-700 text-cyan-300 rounded-lg text-xs font-bold transition-all border border-cyan-500/30 hover:border-cyan-400 cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </button>
          
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-amber-500/20 border border-amber-400/50 rounded-lg shadow-md">
              <Zap className="w-4 h-4 text-amber-300 animate-pulse" />
            </div>
            <div>
              <h1 className="text-xs font-black text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-yellow-400 to-amber-500 uppercase tracking-wider">
                GANGSTAR BYPASS
              </h1>
              <p className="text-[10px] font-mono text-cyan-400/80 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-ping" />
                Module Active on Port 8088
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <a
            href={bypassUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-200 border border-cyan-400/50 rounded-lg text-xs font-bold transition-all cursor-pointer"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open in New Tab
          </a>
        </div>
      </div>

      {/* Frame Principal do Novo Bypass */}
      <div className="flex-1 w-full h-full bg-[#070b19] relative">
        <iframe
          src={bypassUrl}
          title="Gangstar Bypass Panel"
          className="w-full h-full border-0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        />
      </div>
    </div>
  );
}


