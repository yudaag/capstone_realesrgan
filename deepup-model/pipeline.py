"""Depth-aware Real-ESRGAN image/video pipeline adapted from depth_final.ipynb.

The mathematical processing functions are preserved from the capstone notebook.
Colab-only upload, Drive, display, and automatic execution code was removed.
"""

# ============================================================
# IMAGE + VIDEO UNIFIED PIPELINE
#
# 사용법:
#   INPUT_PATH에 이미지 또는 동영상 파일 하나만 지정
#
# 자동 판별:
#   jpg/jpeg/png/... -> IMAGE
#   mp4/mov/avi/...  -> VIDEO
#
# IMAGE:
#   기존 이미지 실험 파이프라인 그대로
#   temporal 없음
#
# VIDEO:
#   동일 core
#   + depth range temporal stabilization
#   + depth temporal
#   + structure temporal
#   + blur temporal
#   + scene cut reset
#   + optical-flow warp
#
# 전제:
#   processor, model, device -> Depth Anything V2 로드 완료
#   upsampler                -> Real-ESRGAN 로드 완료
# ============================================================


import os
import cv2
import torch
import numpy as np
import torch.nn.functional as F

from PIL import Image

processor = None
model = None
device = None
upsampler = None


def configure_models(depth_processor, depth_model, torch_device, realesrgan_upsampler):
    global processor, model, device, upsampler
    processor = depth_processor
    model = depth_model
    device = torch_device
    upsampler = realesrgan_upsampler



# ============================================================
# ★ 1. IMAGE 기본 파라미터
# ============================================================

# IMAGE 실험에서 원본을 LR로 만들어 테스트할지 여부
# VIDEO에는 적용하지 않음
MAKE_LOW_RESOLUTION = False

DOWNSCALE = 8
UPSCALE = 4


# ------------------------------------------------------------
# Depth
#
# 0 = Far
# 1 = Near
# ------------------------------------------------------------

DEPTH_FAR = 0.10
DEPTH_NEAR = 0.30


# ------------------------------------------------------------
# Structure
# ------------------------------------------------------------

EDGE_WEIGHT = 0.4
RESIDUAL_WEIGHT = 0.6

RESIDUAL_PERCENTILE = 80

STRUCTURE_START = 0.15
STRUCTURE_PROTECT_POWER = 0.4


# ------------------------------------------------------------
# Blur
# ------------------------------------------------------------

MIN_STRUCTURE_BLUR = 0.03

BLUR_SIGMA = 2.5

MASK_SIGMA = 0.5


# ============================================================
# ★ 2. VIDEO 전용 파라미터
#
# IMAGE에는 적용되지 않음
# ============================================================

VIDEO_DEPTH_RANGE_ALPHA = 0.95

VIDEO_DEPTH_ALPHA = 0.80

VIDEO_STRUCTURE_ALPHA = 0.70

VIDEO_BLUR_ALPHA = 0.80


# Scene Cut
SCENE_CUT_THRESHOLD = 0.30


# Optical Flow
USE_OPTICAL_FLOW = True


# Debug video 저장
SAVE_DEBUG_VIDEO = False


# ============================================================
# 3. 지원 확장자
# ============================================================

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".m4v",
}


# ============================================================
# 5. VIDEO TEMPORAL STATE
# ============================================================

class TemporalState:

    def __init__(self):

        self.prev_frame = None

        self.prev_depth = None

        self.prev_structure = None

        self.prev_blur = None

        self.depth_low = None

        self.depth_high = None


    def reset(self):

        self.prev_frame = None

        self.prev_depth = None

        self.prev_structure = None

        self.prev_blur = None

        self.depth_low = None

        self.depth_high = None


# ============================================================
# 6. Edge Structure
#
# 기존 IMAGE 코드 그대로
# ============================================================

def make_edge_structure_map(
    img,
    blur_sigma=1.5
):

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    ).astype(np.float32)


    gx = cv2.Sobel(
        gray,
        cv2.CV_32F,
        1,
        0,
        ksize=3
    )


    gy = cv2.Sobel(
        gray,
        cv2.CV_32F,
        0,
        1,
        ksize=3
    )


    mag = np.sqrt(
        gx ** 2
        +
        gy ** 2
    )


    norm = (
        np.percentile(
            mag,
            99
        )
        +
        1e-8
    )


    mag = np.clip(
        mag / norm,
        0.0,
        1.0
    )


    if blur_sigma > 0:

        mag = cv2.GaussianBlur(
            mag,
            (0, 0),
            blur_sigma
        )


    return np.clip(
        mag,
        0.0,
        1.0
    ).astype(np.float32)


# ============================================================
# 7. Residual Structure
#
# 기존 IMAGE 코드 그대로
# ============================================================

def make_residual_structure_map(
    I_up,
    I_sr,
    percentile=80,
    blur_sigma=2.0
):

    diff = np.abs(
        I_sr.astype(np.float32)
        -
        I_up.astype(np.float32)
    )


    diff = np.mean(
        diff,
        axis=2
    )


    threshold = np.percentile(
        diff,
        percentile
    )


    high = np.percentile(
        diff,
        99
    )


    residual = (
        diff - threshold
    ) / (
        high - threshold + 1e-8
    )


    residual = np.clip(
        residual,
        0.0,
        1.0
    )


    if blur_sigma > 0:

        residual = cv2.GaussianBlur(
            residual,
            (0, 0),
            blur_sigma
        )


    return np.clip(
        residual,
        0.0,
        1.0
    ).astype(np.float32)


# ============================================================
# 8. Depth Anything RAW Depth
# ============================================================

@torch.no_grad()
def estimate_raw_depth(
    img_bgr
):

    h, w = img_bgr.shape[:2]


    depth_image = Image.fromarray(
        cv2.cvtColor(
            img_bgr,
            cv2.COLOR_BGR2RGB
        )
    )


    inputs = processor(
        images=depth_image,
        return_tensors="pt"
    )


    inputs = {
        k: v.to(device)
        for k, v in inputs.items()
    }


    outputs = model(
        **inputs
    )


    predicted_depth = (
        outputs.predicted_depth
    )


    depth = F.interpolate(
        predicted_depth.unsqueeze(1),
        size=(h, w),
        mode="bicubic",
        align_corners=False
    ).squeeze()


    depth = (
        depth
        .detach()
        .cpu()
        .numpy()
        .astype(np.float32)
    )


    return depth


# ============================================================
# 9. IMAGE Depth Normalization
#
# 기존 IMAGE 방식 그대로
#
# 각 이미지 자체의 percentile 2 ~ 98
# ============================================================

def normalize_depth_image(
    depth
):

    low = np.percentile(
        depth,
        2
    )


    high = np.percentile(
        depth,
        98
    )


    depth_normalized = (
        (depth - low)
        /
        (high - low + 1e-8)
    )


    depth_normalized = np.clip(
        depth_normalized,
        0.0,
        1.0
    )


    return depth_normalized


# ============================================================
# 10. VIDEO Depth Normalization
#
# VIDEO에서만 percentile range temporal smoothing
# ============================================================

def normalize_depth_video(
    depth,
    state
):

    current_low = np.percentile(
        depth,
        2
    )


    current_high = np.percentile(
        depth,
        98
    )


    if state.depth_low is None:

        state.depth_low = current_low

        state.depth_high = current_high

    else:

        state.depth_low = (
            VIDEO_DEPTH_RANGE_ALPHA
            *
            state.depth_low
            +
            (1.0 - VIDEO_DEPTH_RANGE_ALPHA)
            *
            current_low
        )


        state.depth_high = (
            VIDEO_DEPTH_RANGE_ALPHA
            *
            state.depth_high
            +
            (1.0 - VIDEO_DEPTH_RANGE_ALPHA)
            *
            current_high
        )


    depth_normalized = (
        (depth - state.depth_low)
        /
        (
            state.depth_high
            -
            state.depth_low
            +
            1e-8
        )
    )


    depth_normalized = np.clip(
        depth_normalized,
        0.0,
        1.0
    )


    return depth_normalized


# ============================================================
# 11. Scene Cut Detection
#
# VIDEO ONLY
# ============================================================

def detect_scene_cut(
    prev_frame,
    current_frame
):

    if prev_frame is None:

        return False


    prev_small = cv2.resize(
        prev_frame,
        (64, 64),
        interpolation=cv2.INTER_AREA
    )


    curr_small = cv2.resize(
        current_frame,
        (64, 64),
        interpolation=cv2.INTER_AREA
    )


    prev_hsv = cv2.cvtColor(
        prev_small,
        cv2.COLOR_BGR2HSV
    )


    curr_hsv = cv2.cvtColor(
        curr_small,
        cv2.COLOR_BGR2HSV
    )


    hist_prev = cv2.calcHist(
        [prev_hsv],
        [0, 1],
        None,
        [32, 32],
        [0, 180, 0, 256]
    )


    hist_curr = cv2.calcHist(
        [curr_hsv],
        [0, 1],
        None,
        [32, 32],
        [0, 180, 0, 256]
    )


    cv2.normalize(
        hist_prev,
        hist_prev
    )


    cv2.normalize(
        hist_curr,
        hist_curr
    )


    distance = cv2.compareHist(
        hist_prev,
        hist_curr,
        cv2.HISTCMP_BHATTACHARYYA
    )


    return (
        distance
        >
        SCENE_CUT_THRESHOLD
    )


# ============================================================
# 12. Optical Flow
#
# current -> previous 방향
#
# VIDEO ONLY
# ============================================================

def calculate_backward_flow(
    prev_frame,
    current_frame,
    out_size
):

    out_w, out_h = out_size


    prev_gray = cv2.cvtColor(
        prev_frame,
        cv2.COLOR_BGR2GRAY
    )


    curr_gray = cv2.cvtColor(
        current_frame,
        cv2.COLOR_BGR2GRAY
    )


    flow = cv2.calcOpticalFlowFarneback(
        curr_gray,
        prev_gray,
        None,
        0.5,
        3,
        15,
        3,
        5,
        1.2,
        0
    )


    flow = cv2.resize(
        flow,
        (out_w, out_h),
        interpolation=cv2.INTER_LINEAR
    )


    scale_x = (
        out_w
        /
        prev_frame.shape[1]
    )


    scale_y = (
        out_h
        /
        prev_frame.shape[0]
    )


    flow[..., 0] *= scale_x

    flow[..., 1] *= scale_y


    return flow


# ============================================================
# 13. Previous Map -> Current Frame Warp
#
# VIDEO ONLY
# ============================================================

def warp_previous_map(
    previous_map,
    flow
):

    h, w = previous_map.shape[:2]


    grid_x, grid_y = np.meshgrid(
        np.arange(
            w,
            dtype=np.float32
        ),
        np.arange(
            h,
            dtype=np.float32
        )
    )


    map_x = (
        grid_x
        +
        flow[..., 0]
    )


    map_y = (
        grid_y
        +
        flow[..., 1]
    )


    warped = cv2.remap(
        previous_map.astype(np.float32),
        map_x.astype(np.float32),
        map_y.astype(np.float32),
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE
    )


    return warped


# ============================================================
# 14. Temporal Blend
#
# VIDEO ONLY
#
# alpha 높음
# -> 이전 warped map 비중 높음
# ============================================================

def temporal_blend(
    current,
    previous,
    alpha
):

    if previous is None:

        return current.copy()


    return (
        alpha
        *
        previous
        +
        (1.0 - alpha)
        *
        current
    )


# ============================================================
# 15. 공통 CORE
#
# IMAGE:
#   process_core(frame, state=None)
#
# VIDEO:
#   process_core(frame, state=TemporalState)
#
# 따라서 IMAGE 계산에는 temporal이 들어가지 않음
# ============================================================

def process_core(
    img_bgr,
    state=None
):

    h, w = img_bgr.shape[:2]


    out_w = (
        w
        *
        UPSCALE
    )


    out_h = (
        h
        *
        UPSCALE
    )


    # ========================================================
    # VIDEO ONLY
    # Scene Cut
    # ========================================================

    if state is not None:

        is_scene_cut = detect_scene_cut(
            state.prev_frame,
            img_bgr
        )


        if is_scene_cut:

            print(
                "\nScene cut detected -> temporal reset"
            )

            state.reset()


    # ========================================================
    # Lanczos
    #
    # 구조 계산/비교용
    # ========================================================

    I_up = cv2.resize(
        img_bgr,
        (out_w, out_h),
        interpolation=cv2.INTER_LANCZOS4
    )


    # ========================================================
    # Real-ESRGAN
    #
    # 최종 화질 baseline
    # ========================================================

    with torch.no_grad():

        I_sr, _ = upsampler.enhance(
            img_bgr,
            outscale=UPSCALE
        )


    if I_sr.shape[:2] != (
        out_h,
        out_w
    ):

        I_sr = cv2.resize(
            I_sr,
            (out_w, out_h),
            interpolation=cv2.INTER_CUBIC
        )


    # ========================================================
    # RAW Depth
    # ========================================================

    raw_depth = estimate_raw_depth(
        img_bgr
    )


    # ========================================================
    # Depth Normalization
    #
    # IMAGE = 기존 방식
    # VIDEO = temporal range
    # ========================================================

    if state is None:

        depth_normalized = (
            normalize_depth_image(
                raw_depth
            )
        )

    else:

        depth_normalized = (
            normalize_depth_video(
                raw_depth,
                state
            )
        )


    # ========================================================
    # M_depth
    # ========================================================

    M_depth_2d = cv2.resize(
        depth_normalized,
        (out_w, out_h),
        interpolation=cv2.INTER_CUBIC
    )


    M_depth_2d = cv2.GaussianBlur(
        M_depth_2d,
        (0, 0),
        sigmaX=2.0
    )


    M_depth_2d = np.clip(
        M_depth_2d,
        0.0,
        1.0
    ).astype(np.float32)


    # ========================================================
    # Structure
    # ========================================================

    M_edge = (
        make_edge_structure_map(
            I_up
        )
    )


    M_residual = (
        make_residual_structure_map(
            I_up,
            I_sr,
            percentile=RESIDUAL_PERCENTILE
        )
    )


    M_structure_2d = np.clip(
        EDGE_WEIGHT
        *
        M_edge
        +
        RESIDUAL_WEIGHT
        *
        M_residual,
        0.0,
        1.0
    ).astype(np.float32)


    # ========================================================
    # VIDEO ONLY
    #
    # Optical Flow
    # + Temporal Depth
    # + Temporal Structure
    # ========================================================

    if state is not None:

        warped_depth = None

        warped_structure = None

        warped_blur = None


        if (
            state.prev_frame is not None
            and
            USE_OPTICAL_FLOW
        ):

            flow = calculate_backward_flow(
                state.prev_frame,
                img_bgr,
                (out_w, out_h)
            )


            if state.prev_depth is not None:

                warped_depth = warp_previous_map(
                    state.prev_depth,
                    flow
                )


            if state.prev_structure is not None:

                warped_structure = warp_previous_map(
                    state.prev_structure,
                    flow
                )


            if state.prev_blur is not None:

                warped_blur = warp_previous_map(
                    state.prev_blur,
                    flow
                )


        else:

            warped_depth = (
                state.prev_depth
            )

            warped_structure = (
                state.prev_structure
            )

            warped_blur = (
                state.prev_blur
            )


        # ----------------------------------------------------
        # Depth Temporal
        # ----------------------------------------------------

        M_depth_2d = temporal_blend(
            M_depth_2d,
            warped_depth,
            VIDEO_DEPTH_ALPHA
        )


        M_depth_2d = np.clip(
            M_depth_2d,
            0.0,
            1.0
        )


        # ----------------------------------------------------
        # Structure Temporal
        # ----------------------------------------------------

        M_structure_2d = temporal_blend(
            M_structure_2d,
            warped_structure,
            VIDEO_STRUCTURE_ALPHA
        )


        M_structure_2d = np.clip(
            M_structure_2d,
            0.0,
            1.0
        )


    else:

        warped_blur = None


    # ========================================================
    # 여기부터 IMAGE 기존 계산
    # ========================================================

    D = M_depth_2d

    S = M_structure_2d


    # ========================================================
    # Depth -> Far Strength
    # ========================================================

    far_strength = 1.0 - np.clip(
        (
            D
            -
            DEPTH_FAR
        )
        /
        (
            DEPTH_NEAR
            -
            DEPTH_FAR
            +
            1e-8
        ),
        0.0,
        1.0
    )


    # Smoothstep
    far_strength = (
        far_strength ** 2
        *
        (
            3.0
            -
            2.0
            *
            far_strength
        )
    )


    # ========================================================
    # Structure Protection
    # ========================================================

    structure_protect = np.clip(
        (
            S
            -
            STRUCTURE_START
        )
        /
        (
            1.0
            -
            STRUCTURE_START
            +
            1e-8
        ),
        0.0,
        1.0
    )


    structure_protect = (
        structure_protect
        **
        STRUCTURE_PROTECT_POWER
    )


    # ========================================================
    # Current Blur Strength
    #
    # Far + No Structure
    # -> blur 강함
    #
    # Far + Structure
    # -> blur 억제
    #
    # Near
    # -> blur 거의 없음
    # ========================================================

    blur_current = (
        far_strength
        *
        (
            1.0
            -
            (
                1.0
                -
                MIN_STRUCTURE_BLUR
            )
            *
            structure_protect
        )
    )


    if MASK_SIGMA > 0:

        blur_current = cv2.GaussianBlur(
            blur_current,
            (0, 0),
            sigmaX=MASK_SIGMA
        )


    blur_current = np.clip(
        blur_current,
        0.0,
        1.0
    )


    # ========================================================
    # VIDEO ONLY
    # Blur Temporal
    # ========================================================

    if state is not None:

        blur_strength = temporal_blend(
            blur_current,
            warped_blur,
            VIDEO_BLUR_ALPHA
        )


        blur_strength = np.clip(
            blur_strength,
            0.0,
            1.0
        )


    else:

        # IMAGE는 기존 blur map 그대로
        blur_strength = (
            blur_current
        )


    # ========================================================
    # Real-ESRGAN Blur
    # ========================================================

    I_sr_f = I_sr.astype(
        np.float32
    )


    I_blur = cv2.GaussianBlur(
        I_sr_f,
        (0, 0),
        sigmaX=BLUR_SIGMA,
        sigmaY=BLUR_SIGMA
    )


    # ========================================================
    # Final Proposed
    #
    # Real-ESRGAN ↔ Blurred Real-ESRGAN
    #
    # Lanczos는 최종 합성에 사용하지 않음
    # ========================================================

    A = blur_strength[
        ...,
        None
    ]


    I_final = (
        (1.0 - A)
        *
        I_sr_f
        +
        A
        *
        I_blur
    )


    I_final = np.clip(
        I_final,
        0,
        255
    ).astype(np.uint8)


    # ========================================================
    # Difference
    # ========================================================

    diff_sr_final = np.mean(
        np.abs(
            I_sr.astype(np.float32)
            -
            I_final.astype(np.float32)
        ),
        axis=2
    )


    # ========================================================
    # VIDEO State Update
    # ========================================================

    if state is not None:

        state.prev_frame = (
            img_bgr.copy()
        )


        state.prev_depth = (
            M_depth_2d.copy()
        )


        state.prev_structure = (
            M_structure_2d.copy()
        )


        state.prev_blur = (
            blur_strength.copy()
        )


    # ========================================================
    # Return
    # ========================================================

    return {

        "input":
            img_bgr,

        "lanczos":
            I_up,

        "esrgan":
            I_sr,

        "depth":
            M_depth_2d,

        "edge":
            M_edge,

        "residual":
            M_residual,

        "structure":
            M_structure_2d,

        "far":
            far_strength,

        "structure_protect":
            structure_protect,

        "blur":
            blur_strength,

        "esrgan_blurred":
            np.clip(
                I_blur,
                0,
                255
            ).astype(np.uint8),

        "final":
            I_final,

        "difference":
            diff_sr_final,
    }


# ============================================================
# 16. Float Map 저장 Helper
# ============================================================

def save_float_map(
    path,
    array
):

    array = np.clip(
        array,
        0.0,
        1.0
    )


    cv2.imwrite(
        path,
        (
            array * 255
        ).astype(np.uint8)
    )


# ============================================================
# 17. IMAGE PROCESS
#
# ★ temporal 없음
# ★ 기존 이미지 실험 방식
# ============================================================

def process_image(
    image_path,
    save_path
):

    image_name = os.path.splitext(
        os.path.basename(
            image_path
        )
    )[0]


    experiment_dir = os.path.join(
        save_path,
        image_name
    )


    os.makedirs(
        experiment_dir,
        exist_ok=True
    )


    # --------------------------------------------------------
    # Original Load
    # --------------------------------------------------------

    hr_img = cv2.imread(
        image_path
    )


    if hr_img is None:

        raise FileNotFoundError(
            f"이미지를 읽을 수 없습니다: {image_path}"
        )


    hr_h, hr_w = (
        hr_img.shape[:2]
    )


    # --------------------------------------------------------
    # 기존 IMAGE LR 생성 방식
    # --------------------------------------------------------

    if MAKE_LOW_RESOLUTION:

        lr_w = max(
            1,
            hr_w // DOWNSCALE
        )


        lr_h = max(
            1,
            hr_h // DOWNSCALE
        )


        img_bgr = cv2.resize(
            hr_img,
            (lr_w, lr_h),
            interpolation=cv2.INTER_AREA
        )


    else:

        img_bgr = (
            hr_img.copy()
        )


    h, w = (
        img_bgr.shape[:2]
    )


    print()
    print("======================================")
    print("AUTO DETECTED : IMAGE")
    print("Input         :", image_path)
    print("Original      :", (hr_w, hr_h))
    print("LR            :", (w, h))
    print(
        "SR output     :",
        (
            w * UPSCALE,
            h * UPSCALE
        )
    )
    print("Temporal      : OFF")
    print("======================================")


    # --------------------------------------------------------
    # ★ IMAGE = state=None
    # --------------------------------------------------------

    result = process_core(
        img_bgr,
        state=None
    )


    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    cv2.imwrite(
        os.path.join(
            experiment_dir,
            "00_original.png"
        ),
        hr_img
    )


    cv2.imwrite(
        os.path.join(
            experiment_dir,
            "01_lr_input.png"
        ),
        result["input"]
    )


    cv2.imwrite(
        os.path.join(
            experiment_dir,
            "02_lanczos.png"
        ),
        result["lanczos"]
    )


    cv2.imwrite(
        os.path.join(
            experiment_dir,
            "03_realesrgan.png"
        ),
        result["esrgan"]
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "04_depth_gray.png"
        ),
        result["depth"]
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "06_edge_map.png"
        ),
        result["edge"]
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "07_residual_map.png"
        ),
        result["residual"]
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "08_structure_map.png"
        ),
        result["structure"]
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "09_far_strength.png"
        ),
        result["far"]
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "10_structure_protection.png"
        ),
        result["structure_protect"]
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "11_blur_weight.png"
        ),
        result["blur"]
    )


    cv2.imwrite(
        os.path.join(
            experiment_dir,
            "12_realesrgan_blurred.png"
        ),
        result["esrgan_blurred"]
    )


    cv2.imwrite(
        os.path.join(
            experiment_dir,
            "13_proposed.png"
        ),
        result["final"]
    )


    # --------------------------------------------------------
    # Raw Difference
    # --------------------------------------------------------

    np.save(
        os.path.join(
            experiment_dir,
            "14_difference_raw.npy"
        ),
        result["difference"]
    )


    diff_max = np.percentile(
        result["difference"],
        99
    )


    diff_vis = np.clip(
        result["difference"]
        /
        (
            diff_max
            +
            1e-8
        ),
        0.0,
        1.0
    )


    save_float_map(
        os.path.join(
            experiment_dir,
            "15_difference_gray.png"
        ),
        diff_vis
    )


    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    D = result["depth"]

    S = result["structure"]

    far_strength = (
        result["far"]
    )

    structure_protect = (
        result["structure_protect"]
    )

    blur_strength = (
        result["blur"]
    )


    far_region = (
        far_strength >= 0.5
    )


    structured_region = (
        structure_protect >= 0.5
    )


    far_structured = (
        far_region
        &
        structured_region
    )


    far_nonstructured = (
        far_region
        &
        (~structured_region)
    )


    stats = [

        "TYPE=IMAGE",

        f"IMAGE_PATH={image_path}",

        f"ORIGINAL_SIZE={hr_w}x{hr_h}",

        f"LR_SIZE={w}x{h}",

        f"SR_SIZE="
        f"{w * UPSCALE}x"
        f"{h * UPSCALE}",

        f"DEPTH_FAR={DEPTH_FAR}",

        f"DEPTH_NEAR={DEPTH_NEAR}",

        f"STRUCTURE_START="
        f"{STRUCTURE_START}",

        f"STRUCTURE_PROTECT_POWER="
        f"{STRUCTURE_PROTECT_POWER}",

        f"MIN_STRUCTURE_BLUR="
        f"{MIN_STRUCTURE_BLUR}",

        f"BLUR_SIGMA="
        f"{BLUR_SIGMA}",

        f"MASK_SIGMA="
        f"{MASK_SIGMA}",

        f"depth_mean="
        f"{D.mean():.6f}",

        f"structure_mean="
        f"{S.mean():.6f}",

        f"far_strength_mean="
        f"{far_strength.mean():.6f}",

        f"blur_weight_mean="
        f"{blur_strength.mean():.6f}",

        f"difference_mean="
        f"{result['difference'].mean():.6f}",
    ]


    if np.any(
        far_structured
    ):

        stats.append(
            "far_structure_blur_mean="
            f"{blur_strength[far_structured].mean():.6f}"
        )


    if np.any(
        far_nonstructured
    ):

        stats.append(
            "far_no_structure_blur_mean="
            f"{blur_strength[far_nonstructured].mean():.6f}"
        )


    stats_text = "\n".join(
        stats
    )


    with open(
        os.path.join(
            experiment_dir,
            "19_parameters_and_stats.txt"
        ),
        "w"
    ) as f:

        f.write(
            stats_text
        )


    final_path = os.path.join(
        experiment_dir,
        "13_proposed.png"
    )


    print()
    print("IMAGE COMPLETE")
    print("Final :", final_path)
    print("Saved :", experiment_dir)


    return (
        final_path,
        experiment_dir
    )


# ============================================================
# 18. VIDEO Writer Helper
# ============================================================

# ============================================================
# 18. VIDEO Writer Helper
# ============================================================

def create_writer(
    path,
    fps,
    size
):

    fourcc = cv2.VideoWriter_fourcc(
        *"mp4v"
    )

    writer = cv2.VideoWriter(
        path,
        fourcc,
        fps,
        size
    )

    if not writer.isOpened():

        raise RuntimeError(
            f"VideoWriter 생성 실패: {path}"
        )

    return writer


# ============================================================
# 19. VIDEO PROCESS
#
# IMAGE와 동일하게:
#
# Original Video
#       ↓
# DOWNSCALE
#       ↓
# LR Video
#       ↓
# process_core()
#       ↓
# Real-ESRGAN × UPSCALE
# + Depth
# + Structure
# + Blur
# + Temporal
#       ↓
# Final Video
# ============================================================

def process_video(
    video_path,
    save_path
):

    # ========================================================
    # 이름 / 저장 폴더
    # ========================================================

    video_name = os.path.splitext(
        os.path.basename(
            video_path
        )
    )[0]

    experiment_dir = os.path.join(
        save_path,
        video_name
    )

    os.makedirs(
        experiment_dir,
        exist_ok=True
    )


    # ========================================================
    # Video Open
    # ========================================================

    cap = cv2.VideoCapture(
        video_path
    )

    if not cap.isOpened():

        raise RuntimeError(
            f"동영상을 열 수 없습니다: {video_path}"
        )


    # ========================================================
    # Video Information
    # ========================================================

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    if (
        not np.isfinite(fps)
        or
        fps <= 0
    ):

        fps = 30.0


    frame_count = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )


    input_w = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    input_h = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )


    # ========================================================
    # ★ VIDEO LR SIZE
    #
    # IMAGE와 동일하게 원본을 먼저 저해상도로 만듦
    # ========================================================

    if MAKE_LOW_RESOLUTION:

        lr_w = max(
            1,
            input_w // DOWNSCALE
        )

        lr_h = max(
            1,
            input_h // DOWNSCALE
        )

    else:

        lr_w = input_w
        lr_h = input_h


    # ========================================================
    # ★ Final SR Size
    #
    # process_core에서 LR → UPSCALE
    # ========================================================

    out_w = (
        lr_w
        *
        UPSCALE
    )

    out_h = (
        lr_h
        *
        UPSCALE
    )


    # ========================================================
    # Information
    # ========================================================

    print()
    print("======================================")
    print("AUTO DETECTED : VIDEO")
    print("Input         :", video_path)

    print(
        "Original size :",
        (input_w, input_h)
    )

    print(
        "LR size       :",
        (lr_w, lr_h)
    )

    print(
        "SR output     :",
        (out_w, out_h)
    )

    print(
        "DOWNSCALE     :",
        DOWNSCALE
    )

    print(
        "UPSCALE       :",
        UPSCALE
    )

    print(
        "FPS           :",
        fps
    )

    print(
        "Frames        :",
        frame_count
    )

    print(
        "Temporal      : ON"
    )

    print(
        "Optical Flow  :",
        USE_OPTICAL_FLOW
    )

    print("======================================")


    # ========================================================
    # ★ 1. LR VIDEO PREVIEW
    #
    # 실제 알고리즘에 들어가는 LR 영상 저장
    # ========================================================

    lr_video_path = os.path.join(
        experiment_dir,
        "00_low_resolution_video.mp4"
    )

    writer_lr = create_writer(
        lr_video_path,
        fps,
        (lr_w, lr_h)
    )


    print()
    print("======================================")
    print("CREATING LOW RESOLUTION VIDEO")
    print(
        "Original :",
        (input_w, input_h)
    )
    print(
        "LR       :",
        (lr_w, lr_h)
    )
    print("======================================")


    cap.set(
        cv2.CAP_PROP_POS_FRAMES,
        0
    )

    lr_frame_idx = 0


    while True:

        ret, frame = cap.read()

        if not ret:

            break


        # ----------------------------------------------------
        # Original → LR
        # ----------------------------------------------------

        if MAKE_LOW_RESOLUTION:

            frame_lr = cv2.resize(
                frame,
                (lr_w, lr_h),
                interpolation=cv2.INTER_AREA
            )

        else:

            frame_lr = frame.copy()


        writer_lr.write(
            frame_lr
        )


        lr_frame_idx += 1


        if frame_count > 0:

            print(
                f"\rCreating LR "
                f"{lr_frame_idx}/"
                f"{frame_count}",
                end=""
            )

        else:

            print(
                f"\rCreating LR "
                f"{lr_frame_idx}",
                end=""
            )


    writer_lr.release()


    print()
    print()
    print(
        "LR VIDEO SAVED:",
        lr_video_path
    )


    # ========================================================
    # ★ 본 처리를 위해 첫 프레임으로 되돌림
    # ========================================================

    cap.set(
        cv2.CAP_PROP_POS_FRAMES,
        0
    )


    # ========================================================
    # 2. Main Final Video
    # ========================================================

    final_path = os.path.join(
        experiment_dir,
        "final.mp4"
    )

    writer_final = create_writer(
        final_path,
        fps,
        (out_w, out_h)
    )


    # ========================================================
    # 3. Real-ESRGAN Only Video
    # ========================================================

    esrgan_path = os.path.join(
        experiment_dir,
        "realesrgan.mp4"
    )

    writer_esrgan = create_writer(
        esrgan_path,
        fps,
        (out_w, out_h)
    )


    # ========================================================
    # 4. Debug Videos
    # ========================================================

    debug_writers = {}


    if SAVE_DEBUG_VIDEO:

        debug_keys = [

            "depth",

            "structure",

            "far",

            "structure_protect",

            "blur",

        ]


        for key in debug_keys:

            debug_path = os.path.join(
                experiment_dir,
                f"{key}.mp4"
            )

            debug_writers[key] = (
                create_writer(
                    debug_path,
                    fps,
                    (out_w, out_h)
                )
            )


    # ========================================================
    # ★ VIDEO마다 독립 Temporal State
    # ========================================================

    state = TemporalState()


    frame_idx = 0


    # ========================================================
    # 5. Main Frame Loop
    # ========================================================

    print()
    print("======================================")
    print("START VIDEO PROCESSING")
    print("======================================")


    try:

        while True:

            # =================================================
            # Original Frame Read
            # =================================================

            ret, frame = cap.read()


            if not ret:

                break


            # =================================================
            # ★ Original → LR
            #
            # 여기서 실제 입력 영상의 해상도를 낮춤
            # =================================================

            if MAKE_LOW_RESOLUTION:

                frame_lr = cv2.resize(
                    frame,
                    (lr_w, lr_h),
                    interpolation=cv2.INTER_AREA
                )

            else:

                frame_lr = (
                    frame.copy()
                )


            # =================================================
            # ★ 동일 process_core
            #
            # IMAGE:
            # process_core(img, state=None)
            #
            # VIDEO:
            # process_core(frame_lr, state=state)
            #
            # 즉 VIDEO만 Temporal 추가
            # =================================================

            result = process_core(
                frame_lr,
                state=state
            )


            # =================================================
            # Final Proposed
            # =================================================

            writer_final.write(
                result["final"]
            )


            # =================================================
            # Real-ESRGAN Only
            # =================================================

            writer_esrgan.write(
                result["esrgan"]
            )


            # =================================================
            # Debug Videos
            # =================================================

            if SAVE_DEBUG_VIDEO:

                for key, writer in (
                    debug_writers.items()
                ):

                    m = np.clip(
                        result[key],
                        0.0,
                        1.0
                    )


                    m8 = (
                        m
                        *
                        255
                    ).astype(
                        np.uint8
                    )


                    m_bgr = cv2.cvtColor(
                        m8,
                        cv2.COLOR_GRAY2BGR
                    )


                    writer.write(
                        m_bgr
                    )


            # =================================================
            # Progress
            # =================================================

            frame_idx += 1


            if frame_count > 0:

                print(
                    f"\rProcessing "
                    f"{frame_idx}/"
                    f"{frame_count}",
                    end=""
                )

            else:

                print(
                    f"\rProcessing "
                    f"{frame_idx}",
                    end=""
                )


    # ========================================================
    # 반드시 Release
    # ========================================================

    finally:

        cap.release()

        writer_final.release()

        writer_esrgan.release()


        for writer in (
            debug_writers.values()
        ):

            writer.release()


    # ========================================================
    # Complete
    # ========================================================

    print()
    print()
    print("======================================")
    print("VIDEO COMPLETE")
    print("======================================")

    print(
        "Original size :",
        f"{input_w}x{input_h}"
    )

    print(
        "LR size       :",
        f"{lr_w}x{lr_h}"
    )

    print(
        "SR size       :",
        f"{out_w}x{out_h}"
    )

    print(
        "LR Video      :",
        lr_video_path
    )

    print(
        "Real-ESRGAN   :",
        esrgan_path
    )

    print(
        "Final         :",
        final_path
    )

    print(
        "Saved         :",
        experiment_dir
    )

    print("======================================")


    return (
        final_path,
        experiment_dir
    )

# ============================================================
# 20. ★ IMAGE / VIDEO 자동 판별
#
# 사용자가 MODE 선택할 필요 없음
#
# INPUT_PATH의 확장자를 보고 자동 결정
# ============================================================

def process_media(
    input_path,
    save_path
):

    ext = os.path.splitext(
        input_path
    )[1].lower()


    print()
    print("======================================")
    print("AUTO MEDIA DETECTION")
    print("Input     :", input_path)
    print("Extension :", ext)


    # ========================================================
    # IMAGE
    # ========================================================

    if ext in IMAGE_EXTENSIONS:

        print("Detected  : IMAGE")
        print("======================================")

        return process_image(
            input_path,
            save_path
        )


    # ========================================================
    # VIDEO
    # ========================================================

    elif ext in VIDEO_EXTENSIONS:

        print("Detected  : VIDEO")
        print("======================================")

        return process_video(
            input_path,
            save_path
        )


    # ========================================================
    # Unsupported
    # ========================================================

    else:

        print("Detected  : UNKNOWN")
        print("======================================")

        raise ValueError(
            "지원하지 않는 파일 형식입니다.\n"
            f"입력 확장자: {ext}\n"
            f"지원 IMAGE: {sorted(IMAGE_EXTENSIONS)}\n"
            f"지원 VIDEO: {sorted(VIDEO_EXTENSIONS)}"
        )


