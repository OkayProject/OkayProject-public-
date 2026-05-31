import { useCallback, useEffect, useRef, useState, type ReactElement } from "react";
import { Platform, StyleSheet, Vibration } from "react-native";
import { CameraView } from "expo-camera";
import * as Speech from "expo-speech";

export type FeedbackAlertMethod = "voice" | "vibration" | "flash";

const VIBRATION_DURATION_MS = 350;
const FLASH_DURATION_MS = 1000;
const FLASH_SETTLE_DELAY_MS = 500;
const CAMERA_UNMOUNT_DELAY_MS = 400;
const DEFAULT_SPEECH_TEXT = "음성 알림입니다.";

type AlertMethodFeedbackOptions = {
  vibrationPattern?: number | number[];
  voiceText?: string;
};

export function useAlertMethodFeedback(): {
  playAlertMethodFeedback: (
    method: FeedbackAlertMethod,
    options?: AlertMethodFeedbackOptions,
  ) => Promise<void>;
  flashPreview: ReactElement | null;
} {
  const [isCameraMounted, setIsCameraMounted] = useState(false);
  const [isCameraReady, setIsCameraReady] = useState(false);
  const [isTorchEnabled, setIsTorchEnabled] = useState(false);
  const [isFlashPending, setIsFlashPending] = useState(false);
  const settleTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearFlashTimers = useCallback(() => {
    if (settleTimeoutRef.current) {
      clearTimeout(settleTimeoutRef.current);
      settleTimeoutRef.current = null;
    }

    if (stopTimeoutRef.current) {
      clearTimeout(stopTimeoutRef.current);
      stopTimeoutRef.current = null;
    }

    if (unmountTimeoutRef.current) {
      clearTimeout(unmountTimeoutRef.current);
      unmountTimeoutRef.current = null;
    }
  }, []);

  const finishFlashPreview = useCallback(() => {
    clearFlashTimers();
    setIsFlashPending(false);
    setIsTorchEnabled(false);

    unmountTimeoutRef.current = setTimeout(() => {
      setIsCameraReady(false);
      setIsCameraMounted(false);
      unmountTimeoutRef.current = null;
    }, CAMERA_UNMOUNT_DELAY_MS);
  }, [clearFlashTimers]);

  useEffect(() => {
    return () => {
      clearFlashTimers();
    };
  }, [clearFlashTimers]);

  const startFlashPreview = useCallback(() => {
    clearFlashTimers();
    setIsFlashPending(false);
    setIsTorchEnabled(true);

    settleTimeoutRef.current = setTimeout(() => {
      settleTimeoutRef.current = null;
      stopTimeoutRef.current = setTimeout(() => {
        finishFlashPreview();
      }, FLASH_DURATION_MS);
    }, FLASH_SETTLE_DELAY_MS);
  }, [clearFlashTimers, finishFlashPreview]);

  const handleCameraReady = useCallback(() => {
    setIsCameraReady(true);

    if (isFlashPending) {
      startFlashPreview();
    }
  }, [isFlashPending, startFlashPreview]);

  const pulseFlash = useCallback(async () => {
    if (Platform.OS === "web") {
      return;
    }

    try {
      clearFlashTimers();
      setIsFlashPending(true);
      setIsTorchEnabled(false);

      if (isCameraMounted && isCameraReady) {
        startFlashPreview();
        return;
      }

      setIsCameraReady(false);
      setIsCameraMounted(true);
    } catch (error) {
      console.error("Failed to preview flash alert method", error);
      finishFlashPreview();
    }
  }, [
    clearFlashTimers,
    finishFlashPreview,
    isCameraMounted,
    isCameraReady,
    startFlashPreview,
  ]);

  const playAlertMethodFeedback = useCallback(
    async (method: FeedbackAlertMethod, options?: AlertMethodFeedbackOptions) => {
      if (method === "vibration") {
        Vibration.vibrate(options?.vibrationPattern ?? VIBRATION_DURATION_MS);
        return;
      }

      if (method === "flash") {
        await pulseFlash();
        return;
      }

      if (method === "voice") {
        if (Platform.OS === "web") {
          return;
        }

        Speech.stop();
        Speech.speak(options?.voiceText ?? DEFAULT_SPEECH_TEXT, {
          language: "ko-KR",
          pitch: 1,
          rate: 0.9,
        });
      }
    },
    [pulseFlash],
  );

  return {
    playAlertMethodFeedback,
    flashPreview: isCameraMounted ? (
      <CameraView
        active={isCameraMounted}
        enableTorch={isTorchEnabled}
        facing="back"
        mode="picture"
        onCameraReady={handleCameraReady}
        onMountError={finishFlashPreview}
        style={styles.hiddenCamera}
      />
    ) : null,
  };
}

const styles = StyleSheet.create({
  hiddenCamera: {
    position: "absolute",
    left: -1000,
    top: -1000,
    width: 1,
    height: 1,
    opacity: 0.01,
  },
});
