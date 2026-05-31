import { useState } from "react";
import { Camera, useCameraPermissions } from "expo-camera";
import * as Notifications from "expo-notifications";
import { Alert, Linking, Platform, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { colors, typography } from "../src/constants/theme";
import {
  AppHeader,
  AppScreen,
  PrimaryButton,
  ScreenTitle,
} from "../src/components/okay-ui";

const permissions = [
  ["음성 안내 사용", "재난 상황에서 TTS 음성으로 행동 안내를 제공합니다."],
  ["알림 수신", "위험 상황과 실종자 정보를 알림으로 받을 수 있습니다."],
  ["카메라/플래시 사용", "긴급 상황에서 플래시 알림을 제공할 수 있습니다."],
] as const;

export default function PermissionConsentScreen() {
  const router = useRouter();
  const [, requestCameraPermission] = useCameraPermissions();
  const [isRequesting, setIsRequesting] = useState(false);

  const showPermissionBlockedAlert = (title: string, message: string) => {
    Alert.alert(title, message, [
      { text: "취소", style: "cancel" },
      { text: "설정 열기", onPress: () => Linking.openSettings() },
    ]);
  };

  const requestNotificationPermission = async () => {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    const finalStatus =
      existingStatus === "granted"
        ? existingStatus
        : (
            await Notifications.requestPermissionsAsync({
              ios: {
                allowAlert: true,
                allowBadge: true,
                allowSound: true,
              },
            })
          ).status;

    if (finalStatus !== "granted") {
      showPermissionBlockedAlert(
        "알림 권한이 필요합니다",
        "위험 상황과 실종자 정보를 받으려면 알림 권한을 허용해 주세요.",
      );
      return false;
    }

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("alerts", {
        name: "재난 및 실종 알림",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#D92D20",
      });
    }

    return true;
  };

  const requestCameraAndFlashPermission = async () => {
    const existingPermission = await Camera.getCameraPermissionsAsync();
    const permission = existingPermission.granted
      ? existingPermission
      : await requestCameraPermission();

    if (!permission.granted) {
      showPermissionBlockedAlert(
        "카메라 권한이 필요합니다",
        "긴급 상황에서 후면 플래시 알림을 사용하려면 카메라 권한을 허용해 주세요.",
      );
      return false;
    }

    return true;
  };

  const handleAgreeAndNext = async () => {
    if (isRequesting) {
      return;
    }

    setIsRequesting(true);

    try {
      const notificationGranted = await requestNotificationPermission();
      if (!notificationGranted) {
        return;
      }

      const cameraGranted = await requestCameraAndFlashPermission();
      if (!cameraGranted) {
        return;
      }

      router.push("/location-permission" as never);
    } finally {
      setIsRequesting(false);
    }
  };

  return (
    <AppScreen>
      <View style={styles.content}>
        <AppHeader title="알림 권한" />
        <ScreenTitle>알림 방식 동의</ScreenTitle>

        <View style={styles.cards}>
          {permissions.map(([title, body]) => (
            <View key={title} style={styles.card}>
              <Text style={styles.cardTitle}>{title}</Text>
              <Text style={styles.cardBody}>{body}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.footer}>
        <PrimaryButton onPress={handleAgreeAndNext}>
          {isRequesting ? "권한 확인 중" : "동의하고 다음"}
        </PrimaryButton>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  content: {
    flex: 1,
  },
  cards: {
    marginTop: 68,
    gap: 13,
  },
  card: {
    minHeight: 84,
    borderRadius: 7,
    backgroundColor: colors.card,
    paddingHorizontal: 16,
    justifyContent: "center",
  },
  cardTitle: {
    fontSize: 16,
    lineHeight: 21,
    fontWeight: "700",
    color: colors.text,
    marginBottom: 8,
  },
  cardBody: {
    ...typography.bodyMediumRegular,
    color: colors.text,
  },
  footer: {
    justifyContent: "flex-end",
  },
});
