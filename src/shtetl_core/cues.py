"""Text prompts and numeric gates for Orthodox-dress zero-shot scoring."""

from __future__ import annotations

# Positives: Orthodox / Hasidic / Litvish dress cues. Prefer hat+payot+coat together.
# Bare payot alone is not enough — HEADCOVER_PROMPTS + MIN_HEADCOVER_SCORE gate that.
POSITIVE_PROMPTS = [
    "Hasidic Jewish man with beard sidelocks payot and black hat or shtreimel",
    "Hasidic Jewish man wearing a large round shtreimel fur hat and black coat",
    "Orthodox Jewish man with beard sidelocks black hat and long kapote or rekel coat",
    "Hasidic rebbe with white beard sidelocks and shtreimel fur hat",
    "group of Hasidic Jewish men in black coats streimels hats and payot",
    "Litvish yeshiva man with beard black hat and dark frock coat",
    "elderly Orthodox Jewish rabbi with long white beard black hat and dark coat",
    "Orthodox Jewish man with curled payot sidelocks and black yarmulke or fedora",
]

# Must also fire for a hit: Jewish/Orthodox covering — NOT any dark hat.
# Generic "black hat" / "fedora" alone matched Pathé secular crowds.
HEADCOVER_PROMPTS = [
    "Orthodox Jewish man with beard wearing a black Borsalino fedora and payot",
    "Hasidic Jewish man wearing a large round shtreimel fur hat",
    "Hasidic Jewish man wearing a tall dark spodik hat",
    "Orthodox Jewish man wearing a black yarmulke kippah skullcap",
    "bearded Hasidic man in black hat with visible sidelocks payot",
]

# Must look male (adult man). Compared against FEMALE_PROMPTS so women are rejected.
MALE_PROMPTS = [
    "adult man male person",
    "grown man with male face and male clothing",
    "photograph of a man not a woman",
    "male person upper body",
]

FEMALE_PROMPTS = [
    "adult woman female person",
    "grown woman with female face",
    "photograph of a woman not a man",
    "girl or young woman",
]

# Must show enough person / upper-body shape — not a tight face-only crop.
BODY_PROMPTS = [
    "upper body of a person showing shoulders and chest",
    "person from the chest up with torso and shoulders visible",
    "man wearing a coat with shoulders and upper body in frame",
    "full upper-body portrait including head shoulders and chest",
]

FACE_ONLY_PROMPTS = [
    "extreme close-up of a face only filling the frame",
    "tight headshot face crop with no shoulders visible",
    "face portrait cropped above the neck only",
    "close-up facial photo with no torso or coat visible",
]

# Hard negatives for common false positives in newsreels / Pathé / docs.
NEGATIVE_PROMPTS = [
    "modern business suit and necktie",
    "military uniform and helmet",
    "woman in modern dress",
    "adult woman or girl",
    "blurry crowd of anonymous people",
    "child only no adult man",
    "bare headed clean shaven modern man",
    "bareheaded man with curly hair or sidelocks no hat no yarmulke",
    "man with long curled hair beside ears but uncovered bare head",
    "sports jersey athletic clothing or tracksuit",
    "english gentleman in bowler hat or top hat",
    "man in fedora trilby or homburg hat no sidelocks no payot",
    "victorian or edwardian european man in dark coat and hat",
    "1950s man in overcoat and fedora without Jewish sidelocks",
    "newsreel politician or diplomat in dark overcoat",
    "astronaut space suit or NASA flight gear",
    "police officer or firefighter uniform",
    "catholic priest clerical collar",
    "christian bishop wearing a mitre or white pointed ceremonial hat",
    "eastern orthodox priest in vestments or kamilavka",
    "judge or barrister wearing a powdered wig",
    "muslim man in turban or keffiyeh",
    "sikh man wearing a turban",
    "cowboy hat western clothing",
    "bald or short hair man without beard",
    "film actor or celebrity portrait",
    "close-up face only no body or shoulders",
    "tight headshot with no torso visible",
    "secular european crowd in dark coats at a ceremony",
    "man in dark fedora and overcoat no beard no payot no kippah",
    "british royal pageant or state visit crowd in formal hats",
    "cathedral or abbey ceremony guests in hats",
    # Pathé false-keep clusters (OpenAI was inventing shtreimels on these).
    "english public school boys in school uniforms and caps",
    "cricket players in white flannels and sports caps",
    "garden party society guests in hats and coats",
    "royal or aristocratic outdoor garden reception",
    "space race astronaut or rocket launch crowd",
    "british newsreel crowd of secular men in overcoats",
    "greek or european royalty state visit formal dress",
    "westminster abbey or church anniversary ceremony crowd",
]

# OpenCLIP encoder (ViT-L-14 >> classic OpenAI ViT-B/32 for fine-grained dress cues).
CLIP_MODEL = "ViT-L-14"
CLIP_PRETRAINED = "laion2b_s32b_b82k"
YOLO_WEIGHTS = "yolov8s.pt"

# CLIP pre-filter before vision verify. Soft -0.28 flooded pods (~6–20 segs/video).
# 0.04 flooded Review (~9k rows, mostly AI drops). Default 0.10 matches keep-safe band.
# Keep-safe: human Keeps often raw ~0.11–0.19; Pass rejects stay ≤~0.00 raw.
# 0.12 + MAX_NEG 0.82 clamped almost all Keeps to thr-0.05 (0.07) via neg_ratio.
DEFAULT_SCORE_THRESHOLD = 0.10
# On sharp, large person crops only (see blur.is_high_quality_crop) — borderline
# CLIP scores are more trustworthy than on soft EFG postage stamps.
HQ_SCORE_THRESHOLD = 0.04
MIN_POS_SCORE = 0.22
MIN_HEADCOVER_SCORE = 0.19
MIN_MALE_SCORE = 0.17
MIN_BODY_SCORE = 0.12
# Pass rejects sit at neg/pos ≥~1.01; Keeps cluster ~0.82–0.97. Cap under 1.0.
MAX_NEG_TO_POS_RATIO = 0.98
NEG_SCORE_WEIGHT = 1.05
# When headcover ≥ MIN_HEADCOVER_SCORE, scoring.py caps neg weight at 0.65.
DEFAULT_FPS = 1.5
MIN_SEGMENT_SEC = 3.0
MAX_GAP_SEC = 2.0
MIN_PERSON_AREA = 40 * 80
# Person box must be taller than wide (rejects face-square / head-only boxes).
MIN_PERSON_ASPECT = 1.15
# Absolute min bbox height in px — tiny face crops fail even if area clears.
MIN_PERSON_HEIGHT = 180
# Reject far / soft EFG postage-stamp boxes (gallery stills under ~240px look
# soft even when Laplacian is fooled by grain).
MIN_PERSON_WIDTH = 220
# Laplacian variance on a 256px-normalized crop (legacy raw gate). Soft EFG
# stills often have high raw Lap from pixel noise — blur.py also uses denoise.
MIN_SHARPNESS_LAPLACIAN = 150.0
# After upper-body crop, short side must clear this (see blur.is_blurry_crop).
MIN_CROP_SHORT_SIDE = 240
YOLO_CONF = 0.32
TOP_K_CUES = 1
TOP_K_NEGS = 3
# Compat for older pod handlers that still import this. Current segments.py
# ignores the cap when aggregation is uncapped; keep a high ceiling so a
# partial sync_push cannot break warm-up (ImportError).
MAX_SEGMENTS_PER_VIDEO = 10_000
