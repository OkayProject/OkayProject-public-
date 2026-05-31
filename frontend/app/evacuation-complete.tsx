import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { colors, radius, spacing, typography } from "../src/constants/theme";
import { PrimaryButton, SecondaryButton } from "../src/components/okay-ui";

export default function EvacuationCompleteScreen() {
  const router = useRouter();

  return (
    <View style={styles.screen}>
      <View style={styles.mapLayer}>
        <Text style={styles.mapText}>숙명여대{"\n"}학생회관</Text>
        <View style={styles.dot} />
        <View style={styles.arriveMarker}>
          <Text style={styles.arriveText}>도착</Text>
        </View>
      </View>

      <View style={styles.topControls}>
        <Pressable style={styles.circleButton} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={31} color={colors.text} />
        </Pressable>
        <View style={styles.titlePill}>
          <Text style={styles.title}>대피소 안내</Text>
        </View>
        <Pressable style={styles.circleButton}>
          <Ionicons name="locate-outline" size={34} color={colors.text} />
        </Pressable>
      </View>

      <View style={styles.confirmBox}>
        <View style={styles.confirmIcon}>
          <Ionicons name="shield-checkmark-outline" size={44} color={colors.primary} />
        </View>
        <Text style={styles.confirmTitle}>대피 확인</Text>
        <Text style={styles.confirmQuestion}>안전하게 대피를 완료하셨나요?</Text>
        <Text style={styles.confirmBody}>
          현재 대피소에 도착했다면{"\n"}아래 버튼을 눌러 알려주세요
        </Text>
        <View style={styles.confirmButtons}>
          <SecondaryButton style={styles.confirmButton}>아직 도착 전</SecondaryButton>
          <PrimaryButton
            style={styles.confirmButton}
            onPress={() => router.push("/disaster-caution" as never)}
          >
            대피 완료
          </PrimaryButton>
        </View>
      </View>

      <View style={styles.bottomPanel}>
        <View style={styles.destinationRow}>
          <View style={styles.pinBadge}>
            <Text style={styles.pinText}>도착</Text>
          </View>
          <View>
            <Text style={styles.destinationTitle}>숙명여자대학교 대피소</Text>
            <Text style={styles.destinationMeta}>서울 용산구 효창공원로86길 33</Text>
          </View>
        </View>
        <View style={styles.divider} />
        <View style={styles.destinationRow}>
          <MaterialCommunityIcons name="map-marker-check-outline" size={37} color={colors.primary} />
          <View>
            <Text style={styles.destinationTitle}>숙명여자대학교 대피소 경로 안내중</Text>
            <Text style={styles.destinationMeta}>도보 8분 · 375m</Text>
          </View>
        </View>
        <View style={styles.changeButton}>
          <Ionicons name="search" size={19} color={colors.subText} />
          <Text style={styles.changeText}>대피소 변경하기</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#D9D9D9",
  },
  mapLayer: {
    flex: 1,
    backgroundColor: "#DDE1E0",
    opacity: 0.82,
  },
  mapText: {
    position: "absolute",
    left: 34,
    top: 336,
    fontSize: 24,
    lineHeight: 31,
    fontWeight: "700",
    color: "#7A8EAE",
  },
  dot: {
    position: "absolute",
    top: 171,
    left: 218,
    width: 19,
    height: 19,
    borderRadius: 10,
    backgroundColor: colors.rode,
    borderWidth: 3,
    borderColor: colors.background,
  },
  arriveMarker: {
    position: "absolute",
    top: 112,
    left: 204,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  arriveText: {
    ...typography.arriveText,
    color: colors.background,
    fontSize: 17,
  },
  topControls: {
    position: "absolute",
    top: 66,
    left: 28,
    right: 28,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  circleButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "rgba(255,255,255,0.8)",
    alignItems: "center",
    justifyContent: "center",
  },
  titlePill: {
    height: 36,
    borderRadius: 18,
    paddingHorizontal: 18,
    backgroundColor: "rgba(255,255,255,0.85)",
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    ...typography.titleMedium,
    color: colors.text,
  },
  confirmBox: {
    position: "absolute",
    top: 323,
    left: 65,
    right: 65,
    borderRadius: 27,
    backgroundColor: colors.background,
    paddingHorizontal: 18,
    paddingVertical: 31,
    alignItems: "center",
  },
  confirmIcon: {
    width: 66,
    height: 66,
    borderRadius: 33,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.checkCard,
    marginBottom: 8,
  },
  confirmTitle: {
    ...typography.completeCheck,
    color: colors.text,
    marginBottom: 20,
  },
  confirmQuestion: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
    marginBottom: 21,
  },
  confirmBody: {
    ...typography.bodyMediumRegular,
    color: colors.subText,
    textAlign: "center",
    marginBottom: 16,
  },
  confirmButtons: {
    flexDirection: "row",
    gap: 14,
  },
  confirmButton: {
    flex: 1,
    minHeight: 52,
  },
  bottomPanel: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: radius.borderRadiusXl,
    borderTopRightRadius: radius.borderRadiusXl,
    backgroundColor: "#D9D9D9",
    paddingHorizontal: 35,
    paddingTop: 37,
    paddingBottom: 20,
  },
  destinationRow: {
    flexDirection: "row",
    gap: 14,
    alignItems: "center",
  },
  pinBadge: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  pinText: {
    ...typography.titleMedium,
    color: colors.background,
    fontWeight: "700",
  },
  destinationTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  destinationMeta: {
    ...typography.titleMedium,
    color: colors.subText,
    marginTop: 5,
  },
  divider: {
    height: 1,
    backgroundColor: colors.subText,
    marginVertical: 23,
  },
  changeButton: {
    height: 32,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.subText,
    alignSelf: "center",
    paddingHorizontal: 13,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: 12,
  },
  changeText: {
    ...typography.titleMedium,
    color: colors.subText,
  },
});
