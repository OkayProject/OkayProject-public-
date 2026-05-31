import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  GestureResponderEvent,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";

import { searchKakaoAddresses } from "../src/api/kakaoAddressApi";
import { saveUserProfile } from "../src/api/userProfileApi";
import { colors, radius, spacing, typography } from "../src/constants/theme";
import {
  AppHeader,
  AppScreen,
  InputBox,
  MaterialFieldLabel,
  OptionPill,
  PrimaryButton,
  ScreenTitle,
} from "../src/components/okay-ui";
import {
  clearFrequentPlaces,
  clearUserAddress,
  loadFrequentPlaces,
  loadSavedUserId,
  loadUserAddress,
  loadUserBasicInfo,
  loadUserMobilityInfo,
  saveFrequentPlaces,
  saveUserAddress,
  saveUserId,
  type FrequentPlace,
  type UserAddress,
} from "../src/storage/userProfile";

type FloorOption = "basement" | "first" | "none";
type AddressSearchResult = Omit<UserAddress, "floorOption">;
type SearchTarget = { type: "home" } | { type: "frequent"; index: number };

export default function AddressSettingsScreen() {
  const router = useRouter();
  const { resetAddress } = useLocalSearchParams<{ resetAddress?: string }>();
  const [floorOption, setFloorOption] = useState<FloorOption | null>(null);
  const [selectedAddress, setSelectedAddress] =
    useState<AddressSearchResult | null>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AddressSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [addressError, setAddressError] = useState("");
  const [floorError, setFloorError] = useState("");
  const [profileSaveError, setProfileSaveError] = useState("");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [searchTarget, setSearchTarget] = useState<SearchTarget>({
    type: "home",
  });
  const [frequentPlaces, setFrequentPlaces] = useState<FrequentPlace[]>([]);
  const displayAddress =
    selectedAddress?.name ||
    selectedAddress?.roadAddressName || selectedAddress?.addressName;
  const hasSelectedAddress = Boolean(selectedAddress && displayAddress?.trim());

  useEffect(() => {
    let isMounted = true;

    const loadSavedAddress = async () => {
      if (resetAddress === "1") {
        await Promise.all([clearUserAddress(), clearFrequentPlaces()]);

        if (isMounted) {
          setSelectedAddress(null);
          setFrequentPlaces([]);
          setAddressError("");
          setFloorError("");
        }

        return;
      }

      const [savedAddress, savedFrequentPlaces] = await Promise.all([
        loadUserAddress(),
        loadFrequentPlaces(),
      ]);

      if (!isMounted || !savedAddress) {
        if (isMounted) {
          setFrequentPlaces(savedFrequentPlaces);
        }

        return;
      }

      setFrequentPlaces(savedFrequentPlaces);
      setSelectedAddress({
        name: savedAddress.name,
        addressName: savedAddress.addressName,
        roadAddressName: savedAddress.roadAddressName,
        zoneNo: savedAddress.zoneNo,
        x: savedAddress.x,
        y: savedAddress.y,
        source: savedAddress.source,
      });
      setFloorOption(savedAddress.floorOption);
    };

    void loadSavedAddress();

    return () => {
      isMounted = false;
    };
  }, [resetAddress]);

  const openAddressSearch = (target: SearchTarget) => {
    setSearchTarget(target);
    setSearchQuery("");
    setSearchResults([]);
    setSearchError("");
    setIsSearchOpen(true);
  };

  const handleSearch = async () => {
    setSearchError("");
    setIsSearching(true);

    try {
      const results = await searchKakaoAddresses(searchQuery);
      setSearchResults(results);

      if (results.length === 0) {
        setSearchError("검색 결과가 없습니다.");
      }
    } catch (error) {
      console.error("Failed to search Kakao address", error);
      setSearchError(
        "주소 검색에 실패했습니다. API 키와 네트워크를 확인해 주세요.",
      );
    } finally {
      setIsSearching(false);
    }
  };

  const persistAddress = async (
    address: AddressSearchResult,
    nextFloorOption: FloorOption | null,
  ) => {
    await saveUserAddress({
      ...address,
      floorOption: nextFloorOption,
    });
  };

  const handleSelectAddress = async (address: AddressSearchResult) => {
    setIsSearchOpen(false);
    setSearchQuery("");
    setSearchResults([]);
    setSearchError("");

    if (searchTarget.type === "home") {
      setSelectedAddress(address);
      setAddressError("");
      await persistAddress(address, floorOption);
      return;
    }

    const nextPlaces = [...frequentPlaces];
    nextPlaces[searchTarget.index] = address;
    const normalizedPlaces = nextPlaces.filter(Boolean).slice(0, 3);

    setFrequentPlaces(normalizedPlaces);
    await saveFrequentPlaces(normalizedPlaces);
  };

  const handleRemoveFrequentPlace = async (
    index: number,
    event: GestureResponderEvent,
  ) => {
    event.stopPropagation();

    const nextPlaces = frequentPlaces.filter((_, placeIndex) => placeIndex !== index);
    setFrequentPlaces(nextPlaces);
    await saveFrequentPlaces(nextPlaces);
  };

  const handleFloorOptionChange = (nextFloorOption: FloorOption) => {
    setFloorOption(nextFloorOption);
    setFloorError("");

    if (selectedAddress) {
      void persistAddress(selectedAddress, nextFloorOption);
    }
  };

  const handleNext = async () => {
    setProfileSaveError("");
    if (!hasSelectedAddress) {
      setAddressError("주소를 먼저 찾아 선택해 주세요.");
      return;
    }

    if (!floorOption) {
      setFloorError("거주 층 정보를 선택해 주세요.");
      return;
    }

    if (selectedAddress) {
      await persistAddress(selectedAddress, floorOption);
    }

    const [basicInfo, mobilityInfo, savedUserId] = await Promise.all([
      loadUserBasicInfo(),
      loadUserMobilityInfo(),
      loadSavedUserId(),
    ]);

    if (!basicInfo || !mobilityInfo || !selectedAddress) {
      setProfileSaveError(
        "입력한 사용자 정보를 불러오지 못했습니다. 이전 화면을 확인해 주세요.",
      );
      return;
    }

    setIsSavingProfile(true);

    try {
      const homeAddress = selectedAddress.roadAddressName || selectedAddress.addressName;
      const response = await saveUserProfile({
        user_id: savedUserId,
        name: basicInfo.name,
        phone: basicInfo.phone,
        address: homeAddress,
        home_latitude: Number(selectedAddress.y),
        home_longitude: Number(selectedAddress.x),
        home_address: homeAddress,
        frequent_places: frequentPlaces.map((place, index) => ({
          name:
            place.name ||
            place.roadAddressName ||
            place.addressName ||
            `frequent_place_${index + 1}`,
          address: place.roadAddressName || place.addressName,
          latitude: Number(place.y),
          longitude: Number(place.x),
        })),
        has_disability:
          mobilityInfo.mobilityType === "elderly" ||
          mobilityInfo.mobilityType === "hearing" ||
          mobilityInfo.mobilityType === "visual",
        disability_type: mobilityInfo.mobilityType,
        is_mobility_vulnerable: mobilityInfo.isMobilityVulnerable,
        is_semi_basement_resident: floorOption === "basement",
        notification_enabled: mobilityInfo.alarmMethods.length > 0,
        notification_methods: mobilityInfo.alarmMethods,
      });

      await saveUserId(response.user_id);
      router.push("/missing" as never);
    } catch (error) {
      console.error("Failed to save user profile", error);
      setProfileSaveError(
        "사용자 정보를 저장하지 못했습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요.",
      );
    } finally {
      setIsSavingProfile(false);
    }
  };

  return (
    <AppScreen>
      <AppHeader title="주소 등록" backLabel="기본 정보 입력" showBack />
      <ScreenTitle>주소 및 생활권 설정</ScreenTitle>

      <View style={styles.form}>
        <View style={styles.formBlock}>
          <MaterialFieldLabel icon="home-outline">집</MaterialFieldLabel>
          <InputBox
            placeholder="주소 찾기"
            value={hasSelectedAddress ? displayAddress : undefined}
            onPress={() => openAddressSearch({ type: "home" })}
          />
          {addressError ? (
            <Text style={styles.addressErrorText}>{addressError}</Text>
          ) : null}
        </View>

        <View style={styles.formBlock}>
          <Text style={styles.label}>거주 층 정보</Text>
          <View style={styles.row}>
            <OptionPill
              selected={floorOption === "basement"}
              onPress={() => handleFloorOptionChange("basement")}
            >
              반지하
            </OptionPill>
            <OptionPill
              selected={floorOption === "first"}
              onPress={() => handleFloorOptionChange("first")}
            >
              1층
            </OptionPill>
            <OptionPill
              selected={floorOption === "none"}
              onPress={() => handleFloorOptionChange("none")}
            >
              해당 없음
            </OptionPill>
          </View>
          <Text style={styles.helper}>
            * 현 위치와 침수 위험을 더 정확히 계산하기 위해 사용해요.
          </Text>
          {floorError ? (
            <Text style={styles.addressErrorText}>{floorError}</Text>
          ) : null}
        </View>

        <View style={styles.placesBlock}>
          <View style={styles.placeHeader}>
            <MaterialFieldLabel icon="office-building-outline">
              자주 가는 장소
            </MaterialFieldLabel>
            <Text style={styles.placeHint}>
              * 최대 3개까지 등록할 수 있습니다.
            </Text>
          </View>
          <View style={styles.placeInputs}>
            {frequentPlaces.length === 0 ? (
              <InputBox
                placeholder="자주 가는 장소1"
                onPress={() =>
                  openAddressSearch({ type: "frequent", index: 0 })
                }
              />
            ) : null}
            {frequentPlaces.map((place, index) => (
              <InputBox
                key={`${place.x}-${place.y}-${index}`}
                value={place.name || place.roadAddressName || place.addressName}
                onPress={() => openAddressSearch({ type: "frequent", index })}
                rightAccessory={
                  <Pressable
                    accessibilityLabel="자주 가는 장소 삭제"
                    accessibilityRole="button"
                    hitSlop={10}
                    onPress={(event) =>
                      void handleRemoveFrequentPlace(index, event)
                    }
                    style={({ pressed }) => [
                      styles.removePlaceButton,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Ionicons name="remove" size={22} color={colors.primary} />
                  </Pressable>
                }
              />
            ))}
            {frequentPlaces.length < 3 ? (
              <InputBox
                placeholder="+ 장소 추가"
                onPress={() =>
                  openAddressSearch({
                    type: "frequent",
                    index: frequentPlaces.length,
                  })
                }
              />
            ) : null}
          </View>
        </View>
      </View>

      <View style={styles.footer}>
        {profileSaveError ? (
          <Text style={styles.addressErrorText}>{profileSaveError}</Text>
        ) : null}
        <PrimaryButton onPress={isSavingProfile ? undefined : () => void handleNext()}>
          {isSavingProfile ? "저장 중..." : "다음"}
        </PrimaryButton>
      </View>

      <Modal
        animationType="slide"
        onRequestClose={() => setIsSearchOpen(false)}
        transparent
        visible={isSearchOpen}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          style={styles.modalKeyboardView}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalBox}>
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle}>주소 검색</Text>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => setIsSearchOpen(false)}
                >
                  <Text style={styles.closeText}>닫기</Text>
                </Pressable>
              </View>

              <View style={styles.searchRow}>
                <TextInput
                  autoCapitalize="none"
                  autoCorrect={false}
                  enterKeyHint="search"
                  onChangeText={setSearchQuery}
                  onSubmitEditing={() => void handleSearch()}
                  placeholder="도로명 또는 지번 주소"
                  placeholderTextColor={colors.subText}
                  returnKeyType="search"
                  style={styles.searchInput}
                  value={searchQuery}
                />
                <Pressable
                  accessibilityRole="button"
                  onPress={() => void handleSearch()}
                  style={({ pressed }) => [
                    styles.searchButton,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.searchButtonText}>검색</Text>
                </Pressable>
              </View>

              {isSearching ? (
                <ActivityIndicator
                  color={colors.primary}
                  style={styles.loader}
                />
              ) : null}

              {searchError ? (
                <Text style={styles.errorText}>{searchError}</Text>
              ) : null}

              <ScrollView
                keyboardShouldPersistTaps="handled"
                style={styles.resultList}
              >
                {searchResults.map((result) => {
                  const resultTitle =
                    result.name || result.roadAddressName || result.addressName;
                  const resultAddress =
                    result.roadAddressName || result.addressName;

                  return (
                    <Pressable
                      accessibilityRole="button"
                      key={`${result.x}-${result.y}-${resultTitle}`}
                      onPress={() => void handleSelectAddress(result)}
                      style={({ pressed }) => [
                        styles.resultItem,
                        pressed && styles.pressed,
                      ]}
                    >
                      <Text style={styles.resultAddress}>{resultTitle}</Text>
                      {resultAddress && resultAddress !== resultTitle ? (
                        <Text style={styles.resultSubAddress}>
                          {resultAddress}
                        </Text>
                      ) : null}
                    </Pressable>
                  );
                })}
              </ScrollView>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  form: {
    marginTop: 34,
    gap: 26,
  },
  formBlock: {
    gap: 0,
  },
  row: {
    flexDirection: "row",
    gap: spacing.md,
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
  placesBlock: {
    marginTop: 40,
  },
  placeHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  placeHint: {
    ...typography.helperTiny,
    color: colors.subText,
    marginBottom: spacing.md,
  },
  placeInputs: {
    gap: spacing.md,
  },
  footer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  modalKeyboardView: {
    flex: 1,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.25)",
    justifyContent: "flex-start",
    paddingTop: Platform.select({ ios: 225, default: 185 }),
    paddingHorizontal: spacing.lg,
  },
  modalBox: {
    maxHeight: "58%",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderBottomLeftRadius: 20,
    borderBottomRightRadius: 20,
    backgroundColor: colors.background,
    padding: spacing.lg,
  },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  modalTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  closeText: {
    ...typography.titleMedium,
    color: colors.primary,
    fontWeight: "700",
  },
  searchRow: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  searchInput: {
    flex: 1,
    minHeight: 44,
    borderWidth: 1,
    borderColor: colors.cardLine,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.card,
    paddingHorizontal: spacing.md,
    ...typography.titleMedium,
    color: colors.text,
  },
  searchButton: {
    minHeight: 44,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  searchButtonText: {
    ...typography.titleMedium,
    color: colors.background,
    fontWeight: "700",
  },
  loader: {
    marginTop: spacing.lg,
  },
  errorText: {
    ...typography.helperTiny,
    color: "#D92D20",
    marginTop: spacing.md,
  },
  addressErrorText: {
    ...typography.helperTiny,
    color: "#D92D20",
    marginTop: 8,
  },
  resultList: {
    marginTop: spacing.md,
  },
  resultItem: {
    borderBottomWidth: 1,
    borderBottomColor: colors.cardLine,
    paddingVertical: spacing.md,
  },
  resultAddress: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  resultSubAddress: {
    ...typography.helperTiny,
    color: colors.subText,
    marginTop: 4,
  },
  removePlaceButton: {
    width: 32,
    height: 32,
    marginLeft: spacing.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  pressed: {
    opacity: 0.8,
  },
});
