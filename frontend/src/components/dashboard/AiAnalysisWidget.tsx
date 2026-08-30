import { useState, useEffect } from 'react';
import { Brain, Activity, Zap, Target, Cpu, Wifi, Radio } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface AiStatus {
  scanning: boolean;
  totalNodes: number;
  online: number;
  offline: number;
  scansDone: number;
  lastScan: string;
  neuralEngine: boolean;
}

export default function AiAnalysisWidget() {
  const [status, setStatus] = useState<AiStatus>({
    scanning: false,
    totalNodes: 0,
    online: 0,
    offline: 0,
    scansDone: 0,
    lastScan: '--:--',
    neuralEngine: true,
  });
  const [logs, setLogs] = useState<string[]>([]);
  const [nextScan, setNextScan] = useState('06:02');

  useEffect(() => {
    // Simulate AI status updates
    const interval = setInterval(() => {
      setStatus(prev => ({
        ...prev,
        totalNodes: Math.floor(Math.random() * 5) + 1,
        online: Math.floor(Math.random() * 3) + 1,
        offline: Math.floor(Math.random() * 2),
        scansDone: prev.scansDone + (prev.scanning ? 1 : 0),
      }));
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleScan = () => {
    setStatus(prev => ({ ...prev, scanning: true }));
    setLogs(prev => [
      `> [${new Date().toLocaleTimeString()}] Initiating deep scan protocol...`,
      '> Loading neural engine modules...',
      '> Establishing encrypted link...',
      '> Awaiting for your command, sir',
      '> SYSTEM READY. Auto-scan every 10 minutes.',
      ...prev,
    ].slice(0, 20));
    setTimeout(() => {
      setStatus(prev => ({ ...prev, scanning: false }));
    }, 3000);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="h-6 w-6 text-orange-500" />
          <div>
            <h2 className="text-xl font-bold text-orange-500">AI ANALYSIS</h2>
            <p className="text-[10px] text-orange-400/70 uppercase tracking-widest">K-BOT Intelligence Engine v2.0</p>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-[oklch(0.1_0.01_256)] border border-[oklch(0.2_0.012_256)]">
            <Radio className="h-3 w-3 text-orange-500 animate-pulse" />
            <span className="text-xs text-orange-400">NEXT SCAN: {nextScan}</span>
          </div>
          <Button
            onClick={handleScan}
            disabled={status.scanning}
            className="bg-orange-600 hover:bg-orange-700 text-white text-xs"
          >
            <Zap className="h-3 w-3 mr-1" />
            {status.scanning ? 'SCANNING...' : 'SCAN NOW'}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card className="cyber-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Cpu className="h-5 w-5 text-orange-500" />
              <span className="text-2xl font-bold text-white">{status.totalNodes}</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1 uppercase">Total Nodes</p>
          </CardContent>
        </Card>
        <Card className="cyber-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Wifi className="h-5 w-5 text-green-500" />
              <span className="text-2xl font-bold text-white">{status.online}</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1 uppercase">Online</p>
          </CardContent>
        </Card>
        <Card className="cyber-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Radio className="h-5 w-5 text-red-500" />
              <span className="text-2xl font-bold text-white">{status.offline}</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1 uppercase">Offline</p>
          </CardContent>
        </Card>
        <Card className="cyber-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Target className="h-5 w-5 text-orange-500" />
              <span className="text-2xl font-bold text-white">{status.scansDone}</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1 uppercase">Scans Done</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="cyber-card lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-orange-400 flex items-center gap-2">
              <Activity className="h-4 w-4" />
              K-BOT Analyzer
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="bg-[oklch(0.04_0.005_256)] rounded p-4 font-mono text-xs space-y-1 h-[200px] overflow-y-auto">
              <div className="text-orange-500">K-BOT ANALYZER v2.0 — INITIALIZING...</div>
              <div className="text-green-400/80">{`>`} Loading neural engine modules...</div>
              <div className="text-green-400/80">{`>`} Establishing encrypted link...</div>
              <div className="text-yellow-400/80">{`>`} Awaiting for your command, sir</div>
              <div className="text-yellow-400/80">{`>`} Awaiting for your connection</div>
              <div className="text-green-400/80">{`>`} I will analyze all the pin of their account</div>
              <div className="text-green-400/80">{`>`} I will separate for you</div>
              <div className="text-green-400/80">{`>`} SYSTEM READY. Auto-scan every 10 minutes.</div>
              {logs.map((log, i) => (
                <div key={i} className={log.includes('ERROR') ? 'text-red-400' : 'text-green-400/80'}>
                  {log}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="cyber-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-orange-400 flex items-center gap-2">
              <Brain className="h-4 w-4" />
              K-BOT Analyzer
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-center">
              <div className="h-16 w-16 rounded-full border-2 border-orange-500/30 flex items-center justify-center cyber-glow">
                <Brain className="h-8 w-8 text-orange-500" />
              </div>
            </div>
            <div className="text-center">
              <p className="text-xs text-orange-400 font-semibold">K-BOT ANALYZER</p>
              <p className="text-[10px] text-muted-foreground">INTELLIGENCE ENGINE v2.0</p>
            </div>
            <div className="space-y-2">
              {[
                { icon: Radio, text: 'Awaiting for your command, sir' },
                { icon: Wifi, text: 'Awaiting for your connection' },
                { icon: Target, text: 'I will analyze all the pin of their account' },
                { icon: Zap, text: 'I will separate for you' },
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] text-muted-foreground bg-[oklch(0.06_0.01_256)] rounded px-2 py-1.5">
                  <item.icon className="h-3 w-3 text-orange-500/50" />
                  {item.text}
                </div>
              ))}
            </div>
            <div className="flex items-center justify-center gap-1 text-[10px] text-orange-500">
              <span className="h-1.5 w-1.5 rounded-full bg-orange-500 animate-pulse" />
              NEURAL ENGINE ACTIVE
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
