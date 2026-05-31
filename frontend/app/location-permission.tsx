import { useCallback, useEffect, useState } from "react";
import * as Location from "expo-location";
import { Linking, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { colors, typography } from "../src/constants/theme";
import { AppHeader, AppScreen, PrimaryButton } from "../src/components/okay-ui";

export default function LocationPermissionScreen() {
  const router = useRouter();
  const [isRequesting, setIsRequesting] = useState(false);
  const [permissionStatus, setPermissionStatus] =
    useState<Location.PermissionStatus | null>(null);

  const requestLocationPermission = useCallback(async () => {
    setIsRequesting(true);

    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      setPermissionStatus(status);
    } finally {
      setIsRequesting(false);
    }
  }, []);

  useEffect(() => {
    requestLocationPermission();
  }, [requestLocationPermission]);

  const handleNext = async () => {
    if (isRequesting) {
      return;
    }

    if (permissionStatus === Location.PermissionStatus.GRANTED) {
      router.push("/basic-info" as never);
      return;
    }

    if (permissionStatus === Location.PermissionStatus.DENIED) {
      await Linking.openSettings();
      return;
    }

    await requestLocationPermission();
  };

  return (
    <AppScreen>
      <View style={styles.content}>
        <AppHeader title="위치 권한" />
        <View style={styles.copy}>
          <Text style={styles.title}>위치 권한이 필요합니다</Text>
          <Text style={styles.description}>
            현재 위치를 기준으로 개인별 재난 위험 단계, 가까운 대피소, 주변
            실종자 정보를 제공하기 위해 위치 권한이 필요합니다.
          </Text>
          {permissionStatus === Location.PermissionStatus.DENIED ? (
            <Text style={styles.helperText}>
              위치 권한이 꺼져 있습니다. 설정에서 위치 권한을 허용해 주세요.
            </Text>
          ) : null}
        </View>
      </View>

      <View style={styles.footer}>
        <PrimaryButton onPress={handleNext}>
          {isRequesting
            ? "권한 확인 중"
            : permissionStatus === Location.PermissionStatus.GRANTED
              ? "다음"
              : permissionStatus === Location.PermissionStatus.DENIED
                ? "설정에서 권한 허용"
                : "위치 권한 동의"}
        </PrimaryButton>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  content: {
    flex: 1,
  },
  copy: {
    marginTop: 45,
    gap: 48,
  },
  title: {
    fontSize: 28,
    lineHeight: 36,
    fontWeight: "700",
    color: colors.text,
  },
  description: {
    ...typography.titleMedium,
    color: colors.text,
    lineHeight: 29,
  },
  helperText: {
    ...typography.bodyMediumRegular,
    color: "#D92D20",
  },
  footer: {
    justifyContent: "flex-end",
  },
});
