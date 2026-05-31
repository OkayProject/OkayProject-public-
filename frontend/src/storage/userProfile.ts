import { Platform } from "react-native";
import * as FileSystem from "expo-file-system/legacy";

export type UserBasicInfo = {
  name: string;
  phone: string;
};

export type MobilityType = "elderly" | "hearing" | "visual";
export type AlarmMethod = "voice" | "vibration" | "flash";

export type UserMobilityInfo = {
  isMobilityVulnerable: boolean;
  mobilityType: MobilityType | null;
  alarmMethods: AlarmMethod[];
};

export type UserAddress = {
  name?: string;
  addressName: string;
  roadAddressName: string;
  zoneNo: string;
  x: string;
  y: string;
  source?: string;
  floorOption: "basement" | "first" | "none" | null;
};

export type FrequentPlace = Omit<UserAddress, "floorOption">;

const STORAGE_KEY = "okay-user-basic-info";
const USER_ID_STORAGE_KEY = "okay-user-id";
const MOBILITY_STORAGE_KEY = "okay-user-mobility-info";
const ADDRESS_STORAGE_KEY = "okay-user-address";
const FREQUENT_PLACES_STORAGE_KEY = "frequent_places";
const PROFILE_FILE_URI = FileSystem.documentDirectory
  ? `${FileSystem.documentDirectory}${STORAGE_KEY}.json`
  : null;
const USER_ID_FILE_URI = FileSystem.documentDirectory
  ? `${FileSystem.documentDirectory}${USER_ID_STORAGE_KEY}.json`
  : null;
const MOBILITY_FILE_URI = FileSystem.documentDirectory
  ? `${FileSystem.documentDirectory}${MOBILITY_STORAGE_KEY}.json`
  : null;
const ADDRESS_FILE_URI = FileSystem.documentDirectory
  ? `${FileSystem.documentDirectory}${ADDRESS_STORAGE_KEY}.json`
  : null;
const FREQUENT_PLACES_FILE_URI = FileSystem.documentDirectory
  ? `${FileSystem.documentDirectory}${FREQUENT_PLACES_STORAGE_KEY}.json`
  : null;

export const validateName = (value: string) => {
  const trimmedName = value.trim();

  if (!trimmedName) {
    return "이름을 입력해주세요.";
  }

  if (!/^[가-힣\s]{2,10}$/.test(trimmedName)) {
    return "성과 이름이 올바르게 작성되었는지 확인해주세요.";
  }

  return "";
};

export const validatePhone = (value: string) => {
  const digitsOnly = value.replace(/\D/g, "");

  if (!digitsOnly) {
    return "전화번호를 입력해주세요.";
  }

  if (!/^010\d{8}$/.test(digitsOnly)) {
    return "010으로 시작하는 전화번호를 올바르게 입력하였는지 확인해주세요.";
  }

  return "";
};

const isUserBasicInfo = (value: unknown): value is UserBasicInfo => {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<UserBasicInfo>;
  return (
    typeof candidate.name === "string" && typeof candidate.phone === "string"
  );
};

const isUserId = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value > 0;

const validMobilityTypes = new Set<MobilityType>([
  "elderly",
  "hearing",
  "visual",
]);

const validAlarmMethods = new Set<AlarmMethod>([
  "voice",
  "vibration",
  "flash",
]);

const isAlarmMethod = (value: unknown): value is AlarmMethod =>
  typeof value === "string" && validAlarmMethods.has(value as AlarmMethod);

const isUserMobilityInfo = (value: unknown): value is UserMobilityInfo => {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<UserMobilityInfo>;
  return (
    typeof candidate.isMobilityVulnerable === "boolean" &&
    (candidate.mobilityType === null ||
      (typeof candidate.mobilityType === "string" &&
        validMobilityTypes.has(candidate.mobilityType as MobilityType))) &&
    Array.isArray(candidate.alarmMethods) &&
    candidate.alarmMethods.every(isAlarmMethod)
  );
};

const isUserAddress = (value: unknown): value is UserAddress => {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<UserAddress>;
  const validFloorOptions = ["basement", "first", "none", null];

  return (
    (candidate.name === undefined || typeof candidate.name === "string") &&
    typeof candidate.addressName === "string" &&
    typeof candidate.roadAddressName === "string" &&
    typeof candidate.zoneNo === "string" &&
    typeof candidate.x === "string" &&
    typeof candidate.y === "string" &&
    (candidate.source === undefined || typeof candidate.source === "string") &&
    validFloorOptions.includes(candidate.floorOption ?? null)
  );
};

const isFrequentPlace = (value: unknown): value is FrequentPlace => {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<FrequentPlace>;
  return (
    (candidate.name === undefined || typeof candidate.name === "string") &&
    typeof candidate.addressName === "string" &&
    typeof candidate.roadAddressName === "string" &&
    typeof candidate.zoneNo === "string" &&
    typeof candidate.x === "string" &&
    typeof candidate.y === "string" &&
    (candidate.source === undefined || typeof candidate.source === "string")
  );
};

const isFrequentPlaces = (value: unknown): value is FrequentPlace[] =>
  Array.isArray(value) && value.every(isFrequentPlace);

const normalizeUserBasicInfo = (info: UserBasicInfo): UserBasicInfo => ({
  name: info.name.trim(),
  phone: info.phone.trim(),
});

const normalizeUserMobilityInfo = (
  info: UserMobilityInfo,
): UserMobilityInfo => {
  const alarmMethods = info.alarmMethods.filter(
    (method, index) =>
      validAlarmMethods.has(method) && info.alarmMethods.indexOf(method) === index,
  );

  return {
    isMobilityVulnerable: info.isMobilityVulnerable,
    mobilityType: info.isMobilityVulnerable ? info.mobilityType : null,
    alarmMethods,
  };
};

const normalizeUserAddress = (address: UserAddress): UserAddress => ({
  name: address.name?.trim(),
  addressName: address.addressName.trim(),
  roadAddressName: address.roadAddressName.trim(),
  zoneNo: address.zoneNo.trim(),
  x: address.x.trim(),
  y: address.y.trim(),
  source: address.source?.trim(),
  floorOption: address.floorOption,
});

const normalizeFrequentPlace = (place: FrequentPlace): FrequentPlace => ({
  name: place.name?.trim(),
  addressName: place.addressName.trim(),
  roadAddressName: place.roadAddressName.trim(),
  zoneNo: place.zoneNo.trim(),
  x: place.x.trim(),
  y: place.y.trim(),
  source: place.source?.trim(),
});

export const loadUserBasicInfo = async () => {
  try {
    if (Platform.OS === "web") {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return isUserBasicInfo(parsed) ? parsed : null;
    }

    if (!PROFILE_FILE_URI) {
      return null;
    }

    const fileInfo = await FileSystem.getInfoAsync(PROFILE_FILE_URI);
    if (!fileInfo.exists) {
      return null;
    }

    const saved = await FileSystem.readAsStringAsync(PROFILE_FILE_URI);
    const parsed = JSON.parse(saved);
    return isUserBasicInfo(parsed) ? parsed : null;
  } catch (error) {
    console.error("Failed to load user basic info", error);
    return null;
  }
};

export const saveUserBasicInfo = async (info: UserBasicInfo) => {
  const normalizedInfo = normalizeUserBasicInfo(info);
  const serializedInfo = JSON.stringify(normalizedInfo);

  if (Platform.OS === "web") {
    window.localStorage.setItem(STORAGE_KEY, serializedInfo);
    return;
  }

  if (!PROFILE_FILE_URI) {
    return;
  }

  await FileSystem.writeAsStringAsync(PROFILE_FILE_URI, serializedInfo);
};

export const loadSavedUserId = async () => {
  try {
    if (Platform.OS === "web") {
      const saved = window.localStorage.getItem(USER_ID_STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return isUserId(parsed) ? parsed : null;
    }

    if (!USER_ID_FILE_URI) {
      return null;
    }

    const fileInfo = await FileSystem.getInfoAsync(USER_ID_FILE_URI);
    if (!fileInfo.exists) {
      return null;
    }

    const saved = await FileSystem.readAsStringAsync(USER_ID_FILE_URI);
    const parsed = JSON.parse(saved);
    return isUserId(parsed) ? parsed : null;
  } catch (error) {
    console.error("Failed to load user id", error);
    return null;
  }
};

export const saveUserId = async (userId: number) => {
  if (!isUserId(userId)) {
    return;
  }

  const serializedUserId = JSON.stringify(userId);

  if (Platform.OS === "web") {
    window.localStorage.setItem(USER_ID_STORAGE_KEY, serializedUserId);
    return;
  }

  if (!USER_ID_FILE_URI) {
    return;
  }

  await FileSystem.writeAsStringAsync(USER_ID_FILE_URI, serializedUserId);
};

export const loadUserMobilityInfo = async () => {
  try {
    if (Platform.OS === "web") {
      const saved = window.localStorage.getItem(MOBILITY_STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return isUserMobilityInfo(parsed) ? parsed : null;
    }

    if (!MOBILITY_FILE_URI) {
      return null;
    }

    const fileInfo = await FileSystem.getInfoAsync(MOBILITY_FILE_URI);
    if (!fileInfo.exists) {
      return null;
    }

    const saved = await FileSystem.readAsStringAsync(MOBILITY_FILE_URI);
    const parsed = JSON.parse(saved);
    return isUserMobilityInfo(parsed) ? parsed : null;
  } catch (error) {
    console.error("Failed to load user mobility info", error);
    return null;
  }
};

export const saveUserMobilityInfo = async (info: UserMobilityInfo) => {
  const normalizedInfo = normalizeUserMobilityInfo(info);
  const serializedInfo = JSON.stringify(normalizedInfo);

  if (Platform.OS === "web") {
    window.localStorage.setItem(MOBILITY_STORAGE_KEY, serializedInfo);
    return;
  }

  if (!MOBILITY_FILE_URI) {
    return;
  }

  await FileSystem.writeAsStringAsync(MOBILITY_FILE_URI, serializedInfo);
};

export const loadUserAddress = async () => {
  try {
    if (Platform.OS === "web") {
      const saved = window.localStorage.getItem(ADDRESS_STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return isUserAddress(parsed) ? parsed : null;
    }

    if (!ADDRESS_FILE_URI) {
      return null;
    }

    const fileInfo = await FileSystem.getInfoAsync(ADDRESS_FILE_URI);
    if (!fileInfo.exists) {
      return null;
    }

    const saved = await FileSystem.readAsStringAsync(ADDRESS_FILE_URI);
    const parsed = JSON.parse(saved);
    return isUserAddress(parsed) ? parsed : null;
  } catch (error) {
    console.error("Failed to load user address", error);
    return null;
  }
};

export const saveUserAddress = async (address: UserAddress) => {
  const normalizedAddress = normalizeUserAddress(address);
  const serializedAddress = JSON.stringify(normalizedAddress);

  if (Platform.OS === "web") {
    window.localStorage.setItem(ADDRESS_STORAGE_KEY, serializedAddress);
    return;
  }

  if (!ADDRESS_FILE_URI) {
    return;
  }

  await FileSystem.writeAsStringAsync(ADDRESS_FILE_URI, serializedAddress);
};

export const clearUserAddress = async () => {
  if (Platform.OS === "web") {
    window.localStorage.removeItem(ADDRESS_STORAGE_KEY);
    return;
  }

  if (!ADDRESS_FILE_URI) {
    return;
  }

  const fileInfo = await FileSystem.getInfoAsync(ADDRESS_FILE_URI);
  if (fileInfo.exists) {
    await FileSystem.deleteAsync(ADDRESS_FILE_URI, { idempotent: true });
  }
};

export const loadFrequentPlaces = async () => {
  try {
    if (Platform.OS === "web") {
      const saved = window.localStorage.getItem(FREQUENT_PLACES_STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return isFrequentPlaces(parsed) ? parsed.slice(0, 3) : [];
    }

    if (!FREQUENT_PLACES_FILE_URI) {
      return [];
    }

    const fileInfo = await FileSystem.getInfoAsync(FREQUENT_PLACES_FILE_URI);
    if (!fileInfo.exists) {
      return [];
    }

    const saved = await FileSystem.readAsStringAsync(FREQUENT_PLACES_FILE_URI);
    const parsed = JSON.parse(saved);
    return isFrequentPlaces(parsed) ? parsed.slice(0, 3) : [];
  } catch (error) {
    console.error("Failed to load frequent places", error);
    return [];
  }
};

export const saveFrequentPlaces = async (places: FrequentPlace[]) => {
  const normalizedPlaces = places.slice(0, 3).map(normalizeFrequentPlace);
  const serializedPlaces = JSON.stringify(normalizedPlaces);

  if (Platform.OS === "web") {
    window.localStorage.setItem(FREQUENT_PLACES_STORAGE_KEY, serializedPlaces);
    return;
  }

  if (!FREQUENT_PLACES_FILE_URI) {
    return;
  }

  await FileSystem.writeAsStringAsync(
    FREQUENT_PLACES_FILE_URI,
    serializedPlaces,
  );
};

export const clearFrequentPlaces = async () => {
  if (Platform.OS === "web") {
    window.localStorage.removeItem(FREQUENT_PLACES_STORAGE_KEY);
    return;
  }

  if (!FREQUENT_PLACES_FILE_URI) {
    return;
  }

  const fileInfo = await FileSystem.getInfoAsync(FREQUENT_PLACES_FILE_URI);
  if (fileInfo.exists) {
    await FileSystem.deleteAsync(FREQUENT_PLACES_FILE_URI, {
      idempotent: true,
    });
  }
};
