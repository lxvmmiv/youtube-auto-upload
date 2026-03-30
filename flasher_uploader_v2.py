#!/usr/bin/env python3
"""
Flashing Color Video Generator + YouTube Auto-Uploader

Dependencies (no moviepy needed):
    pip install numpy scipy google-auth google-auth-oauthlib google-api-python-client

FFmpeg must be installed:
    Ubuntu/Debian: sudo apt install ffmpeg
    macOS:         brew install ffmpeg

YouTube Setup:
    1. https://console.cloud.google.com/ → enable YouTube Data API v3
    2. Create OAuth 2.0 credentials (Desktop app) → download as client_secrets.json
    3. Run once — browser opens for auth, token saved to token.json
"""

import os, time, random, datetime, subprocess, logging
import numpy as np
from tqdm import tqdm
from scipy.io.wavfile import write as wav_write

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("flasher.log")]
)
log = logging.getLogger(__name__)

FPS, RESOLUTION, SAMPLE_RATE = 24, (1280, 720), 44100
MIN_DURATION, MAX_DURATION   = 10 * 60, 50 * 60
MIN_FLASH,    MAX_FLASH      = 0.1, 1.5
MIN_FREQ,     MAX_FREQ       = 80, 2000
SCOPES         = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS = "client_secrets.json"
TOKEN_FILE     = "token.json"
UPLOAD_INTERVAL = 3600
OUTPUT_DIR = "output_videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_segments(total):
    segs, elapsed = [], 0.0
    while elapsed < total:
        dur = min(round(random.uniform(MIN_FLASH, MAX_FLASH), 3), total - elapsed)
        segs.append({"r": random.randint(0,255), "g": random.randint(0,255),
                     "b": random.randint(0,255), "freq": random.uniform(MIN_FREQ, MAX_FREQ), "dur": dur})
        elapsed += dur
    return segs


def build_audio(segments, wav_path):
    chunks = []
    for s in tqdm(segments, desc="Building audio", unit="seg"):
        n = int(SAMPLE_RATE * s["dur"])
        t = np.linspace(0, s["dur"], n, endpoint=False)
        w = (0.4 * np.sin(2 * np.pi * s["freq"] * t)).astype(np.float32)
        fade = min(int(SAMPLE_RATE * 0.005), n // 2)
        ramp = np.linspace(0, 1, fade)
        w[:fade] *= ramp; w[-fade:] *= ramp[::-1]
        chunks.append(w)
    stereo = np.column_stack([np.concatenate(chunks)] * 2)
    wav_write(wav_path, SAMPLE_RATE, stereo)


def generate_video(output_path):
    total    = random.uniform(MIN_DURATION, MAX_DURATION)
    log.info(f"Generating {total/60:.1f} min video → {output_path}")
    segments = build_segments(total)
    log.info(f"  {len(segments)} segments")
    W, H     = RESOLUTION
    tmp_wav  = output_path + ".tmp.wav"
    tmp_vid  = output_path + ".tmp.mp4"

    build_audio(segments, tmp_wav)

    proc = subprocess.Popen([
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS), "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", tmp_vid
    ], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    total_frames = sum(max(1, round(s["dur"] * FPS)) for s in segments)
    with tqdm(total=total_frames, desc="Rendering video", unit="frame") as pbar:
        for s in segments:
            frame = np.full((H, W, 3), [s["r"], s["g"], s["b"]], dtype=np.uint8).tobytes()
            n_frames = max(1, round(s["dur"] * FPS))
            for _ in range(n_frames):
                proc.stdin.write(frame)
            pbar.update(n_frames)
    proc.stdin.close(); proc.wait()

    subprocess.run(["ffmpeg", "-y", "-i", tmp_vid, "-i", tmp_wav,
                    "-c:v", "copy", "-c:a", "aac", "-shortest", output_path],
                   check=True, stderr=subprocess.DEVNULL)
    os.remove(tmp_wav); os.remove(tmp_vid)
    log.info(f"  Saved: {output_path}")
    return output_path


def get_youtube_service():
    import json, tempfile
    if not GOOGLE_AVAILABLE:
        raise RuntimeError("Google API libraries not installed.")

    # Load credentials from environment variables (Railway) or local files (Mac)
    client_secrets_str = os.environ.get("CLIENT_SECRETS")
    token_str          = os.environ.get("GOOGLE_TOKEN")

    if client_secrets_str:
        # Write env var contents to temp files
        tmp_secrets = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp_secrets.write(client_secrets_str); tmp_secrets.flush()
        secrets_path = tmp_secrets.name
    elif os.path.exists(CLIENT_SECRETS):
        secrets_path = CLIENT_SECRETS
    else:
        raise FileNotFoundError("No client_secrets.json or CLIENT_SECRETS env var found.")

    if token_str:
        creds = Credentials.from_authorized_user_info(json.loads(token_str), SCOPES)
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update the env var value in token.json for local use
            if not token_str:
                open(TOKEN_FILE, "w").write(creds.to_json())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES).run_local_server(port=0)
            open(TOKEN_FILE, "w").write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


WORDS = [
    "apple","brave","chair","dance","eagle","flame","grace","heart","ideal","jewel",
    "knife","lemon","magic","night","ocean","peace","queen","river","stone","tiger",
    "ultra","vivid","water","xenon","youth","zebra","above","below","catch","depth",
    "earth","faith","giant","honey","image","judge","karma","light","might","nerve",
    "olive","power","quiet","range","solar","trade","unity","value","wrath","yield",
    "angle","beast","cedar","drive","elder","frost","globe","haven","inlet","joker",
    "knack","lunar","maple","noble","orbit","plane","quest","radar","shade","theme",
    "upper","vapor","woods","xylem","zonal","amber","blaze","cloud","drift","ember",
    "flare","gleam","gloom","graze","grind","grove","guard","guide","guile","gusto",
    "habit","haste","haunt","haven","hedge","herbs","heron","hints","hoist","homer",
    "honey","honor","horse","hotel","house","hover","humor","husky","hyena","hyper",
    "blunt","board","boast","boost","booth","bound","boxer","brand","brave","bread",
    "break","breed","brick","bride","bring","brisk","broad","brook","broom","broth",
    "build","built","bulge","bunch","burst","buyer","camel","candy","cargo","carry",
    "catch","cause","cedar","chain","chalk","charm","chase","cheap","check","cheek",
    "chess","chest","chief","child","civic","civil","claim","clamp","clang","clash",
    "clasp","class","clean","clear","clerk","click","cliff","climb","clock","clone",
    "close","cloth","cloud","clout","craft","crane","crash","crawl","craze","cream",
    "creek","crime","crisp","cross","crowd","crown","crush","crust","curve","cycle",
    "daily","dance","daring","dawns","deals","decay","decor","decoy","delay","delta",
    "dense","depot","depth","derby","deter","devil","diary","disco","ditch","diver",
    "dodge","doing","doubt","dough","draft","drain","drama","drape","drawn","dream",
    "dress","drift","drill","drink","drive","drops","drove","drums","dryer","dunce",
    "eagle","earth","eight","elite","epoch","equal","error","essay","event","every",
    "exact","exalt","exile","exist","extra","fable","faint","faith","false","fancy",
    "fault","feast","fence","ferry","fever","fiber","field","fifth","fifty","fight",
    "final","first","fixed","flair","flake","flame","flank","flash","flask","flesh",
    "float","flock","flood","floor","flour","flown","fluid","flute","focus","force",
    "forge","forma","forte","forum","found","frame","frank","fraud","fresh","front",
    "froze","fruit","fully","fungi","funky","funny","gauge","gecko","ghost","given",
    "gland","glass","glide","glint","gloss","glove","going","grace","grade","grain",
    "grand","grant","graph","grasp","grass","gravel","great","green","greet","grief",
    "gripe","groan","groin","groom","gross","group","grove","growl","grown","gruel",
    "grunt","guess","guest","guild","guise","gulch","gully","gummy","guppy","gushy",
    "happy","hardy","harsh","hasty","hateful","heady","heavy","hedge","hefty","hence",
    "herbs","heroic","hilly","hippo","hitch","hoary","holly","homer","hoped","hornet",
    "humid","hurry","husky","ideal","image","imply","inbox","indie","infer","inner",
    "inter","intro","irony","ivory","jazzy","joust","judge","jumbo","jumpy","juror",
    "karma","kayak","keenly","knack","kneel","lance","lanky","lapel","large","laser",
    "latch","later","lavish","layer","leaky","leafy","learn","least","leave","ledge",
    "legal","lemon","level","light","limit","liner","lingo","liner","lofty","logic",
    "loopy","lotus","lover","lower","lucid","lucky","lusty","lyric","magic","major",
    "maker","manor","march","merit","metal","metro","might","miles","mimic","minor",
    "minus","mirth","misty","mixed","model","money","monks","moody","moral","mossy",
    "motor","mount","mouse","mouth","mover","muddy","murky","musty","mystery","naive",
    "nerdy","nerve","never","newer","night","ninja","noble","noisy","north","noted",
    "novel","nymph","offer","often","onset","opera","order","other","ought","outer",
    "outdo","overt","owned","oxide","ozone","paint","papal","parka","party","pasta",
    "patch","pause","payoff","pedal","penny","perky","petal","petty","phase","phone",
    "photo","piano","picky","pilot","pinch","pirate","pitch","pixel","pizza","place",
    "plaid","plain","plant","plaza","plead","pluck","plume","plump","plunk","plush",
    "point","poise","polar","polka","poppy","porky","pouch","poult","pound","prank",
    "prawn","press","price","pride","prime","print","prior","privy","probe","prone",
    "proof","prose","proud","prove","prowl","prude","prune","psalm","pubic","pulse",
    "punch","pupil","purge","purse","pushy","pygmy","quail","qualm","query","quick",
    "quirk","quota","quote","radar","radiant","rally","ranch","rapid","raven","rayon",
    "reach","realm","rebel","recon","redox","reedy","regal","reign","relax","remix",
    "repay","repel","repot","rerun","reset","resin","retro","retry","right","rigid",
    "risky","rival","rivet","robin","robot","rocky","rogue","roomy","roost","rough",
    "round","rowdy","ruler","rumba","runny","rusty","sadly","saint","sandy","satin",
    "sauce","savor","scale","scald","scalp","scamp","scant","scary","scene","scoff",
    "scold","scone","scoop","scope","score","scout","scowl","scram","scrap","scrub",
    "seedy","seize","sense","serum","serve","seven","seven","shaft","shake","shaky",
    "shall","shame","shape","share","shark","sharp","shawl","sheer","shell","shift",
    "shiny","shirt","shock","shore","short","shout","shove","showy","shrug","sight",
    "silly","since","sixth","sixty","sized","skate","skewed","skimp","skivy","skull",
    "slant","slash","sleek","sleet","slept","slice","slide","slim","slime","slimy",
    "sling","sloth","slump","slunk","slurp","smart","smash","smear","smell","smile",
    "smoke","snack","snare","sneak","sniff","snoop","snore","snort","solar","solve",
    "sonic","sorry","south","space","spare","spark","spawn","speak","spell","spend",
    "spice","spill","spine","spite","splat","split","spoke","spook","spoon","sport",
    "spout","spray","spree","sprig","spunk","squad","squat","squid","stack","staff",
    "stage","stain","stale","stalk","stall","stamp","stand","stark","start","stash",
    "state","stays","steam","steel","steep","steer","stern","stick","stiff","still",
    "sting","stink","stock","stomp","stoic","stool","store","storm","story","stout",
    "stove","strap","straw","stray","strip","strut","stuck","study","stump","stung",
    "stunt","style","suave","sugar","suite","sunny","super","surge","swamp","swarm",
    "swear","sweep","sweet","swept","swift","swipe","swirl","swoop","tabby","taboo",
    "taffy","talon","tangy","tango","tapir","taste","tasty","taunt","teach","tempo",
    "tense","tenth","tepid","terms","terse","their","theme","these","thick","thing",
    "third","thorn","those","three","threw","throw","thud","thumb","thump","tidal",
    "timid","tipsy","titan","today","token","tonal","topaz","topic","torch","total",
    "touch","tough","toxic","track","trail","train","tramp","trash","tread","treat",
    "trend","trial","tribe","trick","troop","trout","trove","truce","truly","trump",
    "trunk","trust","truth","tulip","tumor","tuner","tunic","tweak","twirl","twist",
    "tying","udder","uncle","under","unfit","union","unify","untie","unwrap","upset",
    "urban","usage","usher","usual","utter","valid","vault","vaunt","vicar","vigor",
    "viral","visor","vista","vital","vivid","vocal","vodka","voila","voter","vouch",
    "vowed","vowel","waltz","watch","weary","weave","wedge","weedy","weird","whale",
    "wheat","wheel","where","which","while","whiff","whirl","white","whole","whose",
    "widen","wider","windy","witty","woman","women","world","worry","worse","worst",
    "worth","would","wound","wrath","wreak","wreck","wring","wrist","write","wrong",
    "yacht","yearn","yield","young","yours","zesty","zippy","zonal","zooms"
]

def random_words(n=5):
    return " ".join(w.capitalize() for w in random.choices(WORDS, k=n))


def upload_to_youtube(path, youtube):
    dur   = float(subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True).stdout.strip()) / 60
    title = random_words(5)
    desc  = random_words(5)
    body  = {"snippet": {"title": title,
                         "description": desc,
                         "tags": ["flashing", "beep", "random"], "categoryId": "22"},
             "status":  {"privacyStatus": "public"}}
    req  = youtube.videos().insert(part="snippet,status", body=body,
           media_body=MediaFileUpload(path, chunksize=-1, resumable=True, mimetype="video/mp4"))
    log.info(f"Uploading: {title}")
    resp = None
    with tqdm(total=100, desc="Uploading", unit="%", bar_format="{l_bar}{bar}| {n:.0f}/{total}%") as pbar:
        last = 0
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                pbar.update(pct - last)
                last = pct
        pbar.update(100 - last)
    log.info(f"  Done → https://youtu.be/{resp['id']}")
    return resp["id"]


def main():
    log.info("=== Flashing Video Generator + YouTube Uploader ===")
    youtube = None
    if GOOGLE_AVAILABLE and os.path.exists(CLIENT_SECRETS):
        try:
            youtube = get_youtube_service(); log.info("YouTube authenticated.")
        except Exception as e:
            log.warning(f"YouTube auth failed: {e}")
    else:
        log.warning("No client_secrets.json — upload disabled.")

    cycle = 0
    while True:
        cycle += 1
        log.info(f"\n{'='*50}\nCycle #{cycle} — {datetime.datetime.now()}\n{'='*50}")
        path = os.path.join(OUTPUT_DIR, f"flash_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        try:
            generate_video(path)
        except Exception as e:
            log.error(f"Generation failed: {e}", exc_info=True); time.sleep(60); continue
        if youtube:
            try: upload_to_youtube(path, youtube)
            except Exception as e: log.error(f"Upload failed: {e}", exc_info=True)
        else:
            log.info("Skipping upload.")
        log.info(f"Sleeping {UPLOAD_INTERVAL//60} min until next cycle…")
        for _ in tqdm(range(UPLOAD_INTERVAL), desc="Next upload in", unit="s", bar_format="{l_bar}{bar}| {remaining} remaining"):
            time.sleep(1)

if __name__ == "__main__":
    main()
