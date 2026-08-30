import {{ useState, useEffect }} from 'react';
import {{ useDeviceData }} from '@/hooks/useDeviceData';
import {{ Card, CardContent, CardHeader, CardTitle }} from '@/components/ui/card';
import {{ Button }} from '@/components/ui/button';
import {{ Radio }} from 'lucide-react';
import {{ usePermission }} from '@/hooks/usePermission';

export default function Pushnotif({{ deviceId }}: {{ deviceId: string }}) {{
  const {{ sendCommand, data, loading }} = useDeviceData(deviceId);
  const canCommand = usePermission('device:command');
  const [active, setActive] = useState(false);

  useEffect(() => {{
    if (deviceId) sendCommand('0xPN', {{ action: 'status' }});
  }}, [deviceId]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-orange-500 flex items-center gap-2">
          <Radio className="h-6 w-6" />
          Push Notifications
        </h2>
        <div className="flex gap-2">
          {canCommand && (
            <Button
              variant={active ? "destructive" : "default"}
              onClick={() => {{
                setActive(!active);
                sendCommand('0xPN', {{ action: active ? 'stop' : 'start' }});
              }}
              className="bg-orange-600 hover:bg-orange-700"
            >
              {{active ? 'Stop' : 'Start'}}
            </Button>
          )}
        </div>
      </div>

      <Card className="bg-slate-900 border-orange-900/30">
        <CardHeader>
          <CardTitle className="text-slate-200">Status</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="text-sm text-orange-400 font-mono bg-slate-950 p-4 rounded overflow-auto">
            {{JSON.stringify(data, null, 2)}}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}}
