import { useCallback, type ReactElement } from "react";

import { loadAlertMethods, type AlertMethod } from "../storage/alertPreferences";
import { loadUserMobilityInfo, type MobilityType } from "../storage/userProfile";
import { useAlertMethodFeedback } from "./useAlertMethodFeedback";

export type RiskAlertLevel = "caution" | "danger" | "emergency";

type RiskAlertFeedbackPlan = {
  vibrationPattern: number | number[];
  flashRepeatCount: number;
  voiceText: string | null;
};

const FLASH_REPEAT_GAP_MS = 450;
const FLASH_SINGLE_CYCLE_MS = 1900;

const riskAlertFeedbackPlans: Record<RiskAlertLevel, RiskAlertFeedbackPlan> = {
  caution: {
    vibrationPattern: 350,
    flashRepeatCount: 1,
    voiceText: "침수 주의 단계입니다. 현재 위치와 이동 경로를 확인해 주세요.",
  },
  danger: {
    vibrationPattern: [0, 450, 300, 450, 300, 450],
    flashRepeatCount: 2,
    voiceText:
      "침수 위험 단계입니다. 저지대 이동을 피하고 안전한 장소로 이동을 준비해 주세요.",
  },
  emergency: {
    vibrationPattern: [0, 700, 200, 700, 200, 700, 200, 700],
    flashRepeatCount: 4,
    voiceText:
      "침수 긴급 단계입니다. 즉시 안전한 장소로 이동하거나 도움을 요청해 주세요.",
  },
};

const sleep = (durationMs: number) =>
  new Promise((resolve) => {
    setTimeout(resolve, durationMs);
  });

function shouldPlayFlash(
  level: RiskAlertLevel,
  mobilityType: MobilityType | null | undefined,
) {
  return level !== "caution" || mobilityType === "hearing";
}

function shouldPlayVoice(
  level: RiskAlertLevel,
  mobilityType: MobilityType | null | undefined,
) {
  return level !== "caution" || mobilityType === "visual";
}

function hasMethod(methods: AlertMethod[], method: AlertMethod) {
  return methods.includes(method);
}

export function useRiskAlertFeedback(): {
  playRiskAlertFeedback: (level: RiskAlertLevel) => Promise<void>;
  flashPreview: ReactElement | null;
} {
  const { playAlertMethodFeedback, flashPreview } = useAlertMethodFeedback();

  const playFlashPattern = useCallback(
    async (repeatCount: number) => {
      for (let index = 0; index < repeatCount; index += 1) {
        await playAlertMethodFeedback("flash");

        if (index < repeatCount - 1) {
          await sleep(FLASH_SINGLE_CYCLE_MS + FLASH_REPEAT_GAP_MS);
        }
      }
    },
    [playAlertMethodFeedback],
  );

  const playRiskAlertFeedback = useCallback(
    async (level: RiskAlertLevel) => {
      const [alertMethods, mobilityInfo] = await Promise.all([
        loadAlertMethods(),
        loadUserMobilityInfo(),
      ]);
      const plan = riskAlertFeedbackPlans[level];
      const mobilityType = mobilityInfo?.mobilityType;

      if (hasMethod(alertMethods, "vibration")) {
        void playAlertMethodFeedback("vibration", {
          vibrationPattern: plan.vibrationPattern,
        });
      }

      if (
        hasMethod(alertMethods, "voice") &&
        plan.voiceText &&
        shouldPlayVoice(level, mobilityType)
      ) {
        void playAlertMethodFeedback("voice", {
          voiceText: plan.voiceText,
        });
      }

      if (
        hasMethod(alertMethods, "flash") &&
        shouldPlayFlash(level, mobilityType)
      ) {
        await playFlashPattern(plan.flashRepeatCount);
      }
    },
    [playAlertMethodFeedback, playFlashPattern],
  );

  return {
    playRiskAlertFeedback,
    flashPreview,
  };
}
