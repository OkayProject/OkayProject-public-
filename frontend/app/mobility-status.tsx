import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { colors, spacing, typography } from "../src/constants/theme";
import {
  AppHeader,
  AppScreen,
  FieldLabel,
  MaterialFieldLabel,
  OptionPill,
  PrimaryButton,
  ScreenTitle,
} from "../src/components/okay-ui";
import { useAlertMethodFeedback } from "../src/hooks/useAlertMethodFeedback";
import { saveAlertMethods } from "../src/storage/alertPreferences";
import { saveUserMobilityInfo } from "../src/storage/userProfile";

type MobilityAnswer = "yes" | "no";
type MobilityType = "elderly" | "hearing" | "visual";
type AlarmMethod = "voice" | "vibration" | "flash";

const recommendedMethods: Record<MobilityType, AlarmMethod[]> = {
  elderly: ["voice"],
  hearing: ["vibration", "flash"],
  visual: ["voice", "vibration"],
};

export default function MobilityStatusScreen() {
  const router = useRouter();
  const { playAlertMethodFeedback, flashPreview } = useAlertMethodFeedback();
  const [mobilityAnswer, setMobilityAnswer] = useState<MobilityAnswer | null>(null);
  const [mobilityType, setMobilityType] = useState<MobilityType | null>(null);
  const [alarmMethods, setAlarmMethods] = useState<AlarmMethod[]>([]);
  const [mobilityError, setMobilityError] = useState("");
  const [mobilityTypeError, setMobilityTypeError] = useState("");
  const [alarmError, setAlarmError] = useState("");

  const selectMobilityAnswer = (answer: MobilityAnswer) => {
    setMobilityAnswer(answer);
    setMobilityType(null);
    setAlarmMethods([]);
    setMobilityError("");
    setMobilityTypeError("");
    setAlarmError("");
  };

  const selectMobilityType = (type: MobilityType) => {
    const nextRecommendedMethods = recommendedMethods[type];

    setMobilityType(type);
    setAlarmMethods(nextRecommendedMethods);
    setMobilityTypeError("");
    setAlarmError("");

    nextRecommendedMethods.forEach((method) => {
      void playAlertMethodFeedback(method);
    });
  };

  const toggleAlarmMethod = (method: AlarmMethod) => {
    const isSelecting = !alarmMethods.includes(method);

    setAlarmMethods((current) =>
      current.includes(method)
        ? current.filter((item) => item !== method)
        : [...current, method],
    );
    setAlarmError("");

    if (isSelecting) {
      void playAlertMethodFeedback(method);
    }
  };

  const showMobilityType = mobilityAnswer === "yes";
  const showHelper = mobilityAnswer === "yes" && mobilityType !== null;

  const handleNext = async () => {
    if (!mobilityAnswer) {
      setMobilityError("이동약자 여부를 선택해 주세요.");
      return;
    }

    if (showMobilityType && !mobilityType) {
      setMobilityTypeError("이동약자 유형을 선택해 주세요.");
      return;
    }

    if (alarmMethods.length === 0) {
      setAlarmError("주요 알림 방식을 선택해 주세요.");
      return;
    }

    await Promise.all([
      saveUserMobilityInfo({
        isMobilityVulnerable: mobilityAnswer === "yes",
        mobilityType: mobilityAnswer === "yes" ? mobilityType : null,
        alarmMethods,
      }),
      saveAlertMethods(alarmMethods),
    ]);

    router.push("/address-settings?resetAddress=1" as never);
  };

  return (
    <AppScreen>
      {flashPreview}
      <AppHeader title="기본 정보 입력" backLabel="기본 정보 입력" showBack />
      <ScreenTitle>사용자 기본 정보</ScreenTitle>

      <View style={styles.form}>
        <View>
          <MaterialFieldLabel icon="human-cane">이동약자 여부</MaterialFieldLabel>
          <View style={styles.row}>
            <OptionPill
              selected={mobilityAnswer === "yes"}
              onPress={() => selectMobilityAnswer("yes")}
            >
              예
            </OptionPill>
            <OptionPill
              selected={mobilityAnswer === "no"}
              onPress={() => selectMobilityAnswer("no")}
            >
              아니요
            </OptionPill>
          </View>
          {mobilityError ? (
            <Text style={styles.errorText}>{mobilityError}</Text>
          ) : null}
        </View>

        {showMobilityType ? (
          <View>
            <Text style={styles.label}>이동약자 유형</Text>
            <View style={styles.compactRow}>
              <OptionPill
                selected={mobilityType === "elderly"}
                onPress={() => selectMobilityType("elderly")}
                style={styles.wideTypePill}
              >
                고령/보행불편(휠체어)
              </OptionPill>
              <OptionPill
                selected={mobilityType === "hearing"}
                onPress={() => selectMobilityType("hearing")}
                style={styles.narrowTypePill}
              >
                청각 장애
              </OptionPill>
              <OptionPill
                selected={mobilityType === "visual"}
                onPress={() => selectMobilityType("visual")}
                style={styles.narrowTypePill}
              >
                시각 장애
              </OptionPill>
            </View>
            {mobilityTypeError ? (
              <Text style={styles.errorText}>{mobilityTypeError}</Text>
            ) : null}
          </View>
        ) : null}

        {mobilityAnswer !== null ? (
          <View>
            <FieldLabel icon="notifications-outline">주요 알림 방식</FieldLabel>
            <View style={styles.row}>
              <OptionPill
                selected={alarmMethods.includes("voice")}
                onPress={() => toggleAlarmMethod("voice")}
              >
                음성
              </OptionPill>
              <OptionPill
                selected={alarmMethods.includes("vibration")}
                onPress={() => toggleAlarmMethod("vibration")}
              >
                진동
              </OptionPill>
              <OptionPill
                selected={alarmMethods.includes("flash")}
                onPress={() => toggleAlarmMethod("flash")}
              >
                플래시
              </OptionPill>
            </View>
            {showHelper ? (
              <Text style={styles.helper}>
                *선택하신 이동 지원 정보에 맞춰 알림 방식을 추천했어요.
              </Text>
            ) : null}
            {alarmError ? (
              <Text style={styles.errorText}>{alarmError}</Text>
            ) : null}
          </View>
        ) : null}
      </View>

      <View style={styles.footer}>
        <PrimaryButton onPress={() => void handleNext()}>다음</PrimaryButton>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  form: {
    marginTop: 34,
    gap: 22,
  },
  row: {
    flexDirection: "row",
    gap: spacing.md,
  },
  compactRow: {
    flexDirection: "row",
    gap: spacing.md,
  },
  wideTypePill: {
    flex: 1.9,
    minHeight: 44,
    paddingHorizontal: 5,
  },
  narrowTypePill: {
    flex: 1,
    minHeight: 44,
    paddingHorizontal: 5,
  },
  label: {
    ...typography.titleMedium,
    color: colors.text,
    marginBottom: spacing.md,
  },
  helper: {
    ...typography.helperTiny,
    color: colors.subText,
    marginTop: 12,
  },
  errorText: {
    ...typography.helperTiny,
    color: "#D92D20",
    marginTop: 8,
  },
  footer: {
    flex: 1,
    justifyContent: "flex-end",
  },
});
