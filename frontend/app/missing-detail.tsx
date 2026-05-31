import { StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";

import { colors, typography } from "../src/constants/theme";
import {
  AppHeader,
  AppScreen,
  Card,
  HeaderActions,
  StatusBadge,
} from "../src/components/okay-ui";
import { MissingReferenceImage } from "../src/components/missing-reference-image";

export default function MissingDetailScreen() {
  const { missingPersonId } = useLocalSearchParams<{
    missingPersonId?: string;
  }>();
  const currentMissingPersonId =
    typeof missingPersonId === "string" ? missingPersonId : "";

  return (
    <AppScreen>
      <AppHeader
        title="실종자 상세 이미지"
        showBack
        right={<HeaderActions />}
      />
      <View style={styles.statusLine}>
        <StatusBadge>현재 수색 중</StatusBadge>
        <Text style={styles.lastSeen}>
          최종 목격 <Text style={styles.red}>확인 중</Text>
        </Text>
      </View>
      <Card style={styles.imageCard}>
        {currentMissingPersonId ? (
          <MissingReferenceImage missingPersonId={currentMissingPersonId} />
        ) : (
          <Text style={styles.emptyText}>
            실종자 정보를 불러올 수 없습니다.
          </Text>
        )}
      </Card>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  statusLine: {
    flexDirection: "row",
    alignItems: "center",
    gap: 17,
    marginBottom: 8,
  },
  lastSeen: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  red: {
    color: colors.primary,
  },
  imageCard: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  emptyText: {
    ...typography.bodyMediumRegular,
    color: colors.subText,
    textAlign: "center",
  },
});
