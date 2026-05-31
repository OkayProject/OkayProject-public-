import { StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { colors, typography } from "../src/constants/theme";
import { AppScreen, PrimaryButton } from "../src/components/okay-ui";

export default function OnboardingScreen() {
  const router = useRouter();

  return (
    <AppScreen contentStyle={styles.content}>
      <View style={styles.copy}>
        <Text style={styles.title}>내곁안전에 오신 것을 환영합니다</Text>
        <Text style={styles.description}>
          내곁안전은 사용자의 위치와 기본 정보를 바탕으로 재난 위험 상황과
          실종자 정보를 알려주는 안전 알림 서비스입니다.
        </Text>
        <PrimaryButton onPress={() => router.push("/permission-consent")}>
          시작하기
        </PrimaryButton>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  content: {
    justifyContent: "center",
  },
  copy: {
    gap: 26,
  },
  title: {
    fontSize: 25,
    lineHeight: 31,
    fontWeight: "700",
    color: colors.text,
    textAlign: "center",
  },
  description: {
    ...typography.bodyMediumRegular,
    color: colors.text,
    textAlign: "center",
    paddingHorizontal: 25,
  },
});
