import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  View,
  type ImageStyle,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { Image } from "expo-image";

import {
  fetchMissingReferenceImage,
  getCachedMissingReferenceImage,
  type MissingReferenceImageResponse,
} from "../api/missingReferenceImageApi";
import { colors } from "../constants/theme";

type MissingReferenceImageProps = {
  missingPersonId: string;
  style?: StyleProp<ViewStyle>;
  imageStyle?: StyleProp<ImageStyle>;
};

export function MissingReferenceImage({
  missingPersonId,
  style,
  imageStyle,
}: MissingReferenceImageProps) {
  const cachedReferenceImage = getCachedMissingReferenceImage(missingPersonId);
  const [isLoading, setIsLoading] = useState(!cachedReferenceImage);
  const [referenceImage, setReferenceImage] =
    useState<MissingReferenceImageResponse | null>(cachedReferenceImage);

  useEffect(() => {
    let isMounted = true;
    const cachedImage = getCachedMissingReferenceImage(missingPersonId);

    if (cachedImage) {
      setReferenceImage(cachedImage);
      setIsLoading(false);
      return () => {
        isMounted = false;
      };
    }

    async function loadReferenceImage() {
      try {
        setIsLoading(true);
        const nextReferenceImage =
          await fetchMissingReferenceImage(missingPersonId);

        if (isMounted) {
          setReferenceImage(nextReferenceImage);
        }
      } catch {
        if (isMounted) {
          setReferenceImage({
            reference_image_url: null,
            status: "failed",
            is_ai_generated: false,
            message: "현재 참고 이미지를 불러올 수 없습니다.",
          });
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadReferenceImage();

    return () => {
      isMounted = false;
    };
  }, [missingPersonId]);

  const imageUrl = referenceImage?.reference_image_url ?? "";
  const canShowGeneratedImage =
    (referenceImage?.status === "completed" || referenceImage?.status === "success") &&
    imageUrl.length > 0;

  return (
    <View style={[styles.wrap, style]}>
      {canShowGeneratedImage ? (
        <Image
          accessibilityLabel="AI 생성 실종자 전신 참고 이미지"
          source={{ uri: imageUrl }}
          resizeMode="contain"
          cachePolicy="memory-disk"
          style={[styles.generatedImage, imageStyle]}
        />
      ) : (
        <View style={styles.emptyState} />
      )}

      {isLoading ? (
        <View style={styles.centerStatus}>
          <ActivityIndicator color={colors.primary} />
          <Text style={styles.statusText}>참고 이미지 생성 중</Text>
        </View>
      ) : null}

      {!isLoading && referenceImage?.status === "failed" ? (
        <View style={styles.centerStatus}>
          <Text style={styles.statusText}>
            {referenceImage.message ?? "현재 참고 이미지를 불러올 수 없습니다."}
          </Text>
        </View>
      ) : null}

      {canShowGeneratedImage && referenceImage?.is_ai_generated ? (
        <View style={styles.notice}>
          <Text style={styles.noticeText}>
            {referenceImage.notice ??
              "AI 생성 참고 이미지이며 실제 모습과 다를 수 있습니다."}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: "100%",
    height: "100%",
    alignItems: "center",
    justifyContent: "center",
  },
  generatedImage: {
    width: "100%",
    height: "100%",
  },
  emptyState: {
    width: "100%",
    height: "100%",
  },
  centerStatus: {
    position: "absolute",
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    paddingHorizontal: 14,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  statusText: {
    fontSize: 15,
    lineHeight: 20,
    fontWeight: "700",
    color: colors.text,
    textAlign: "center",
  },
  notice: {
    position: "absolute",
    left: 8,
    right: 8,
    bottom: 8,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 6,
    backgroundColor: "rgba(255, 255, 255, 0.92)",
  },
  noticeText: {
    fontSize: 11,
    lineHeight: 14,
    fontWeight: "500",
    color: colors.subText,
    textAlign: "center",
  },
});
