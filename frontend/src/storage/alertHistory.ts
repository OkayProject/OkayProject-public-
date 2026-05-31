import { Platform } from "react-native";
import * as FileSystem from "expo-file-system/legacy";

export type AlertHistoryType = "flood" | "missing";
export type AlertHistoryRiskLevel = "caution" | "danger" | "emergency";

export type AlertHistoryItem = {
  id: string;
  type: AlertHistoryType;
  riskLevel?: AlertHistoryRiskLevel | null;
  title: string;
  message: string;
  meta?: string;
  receivedAt: string;
};

type NotificationContent = {
  title?: string | null;
  body?: string | null;
  data?: Record<string, unknown>;
};

const ALERT_HISTORY_STORAGE_KEY = "okay-alert-history";
const ALERT_HISTORY_FILE_URI = FileSystem.documentDirectory
  ? `${FileSystem.documentDirectory}${ALERT_HISTORY_STORAGE_KEY}.json`
  : null;

const validAlertTypes = new Set<AlertHistoryType>(["flood", "missing"]);
const validRiskLevels = new Set<AlertHistoryRiskLevel>([
  "caution",
  "danger",
  "emergency",
]);

const isAlertHistoryItem = (value: unknown): value is AlertHistoryItem => {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<AlertHistoryItem>;

  return (
    typeof candidate.id === "string" &&
    typeof candidate.type === "string" &&
    validAlertTypes.has(candidate.type as AlertHistoryType) &&
    (candidate.riskLevel === undefined ||
      candidate.riskLevel === null ||
      (typeof candidate.riskLevel === "string" &&
        validRiskLevels.has(candidate.riskLevel as AlertHistoryRiskLevel))) &&
    typeof candidate.title === "string" &&
    typeof candidate.message === "string" &&
    (candidate.meta === undefined || typeof candidate.meta === "string") &&
    typeof candidate.receivedAt === "string" &&
    !Number.isNaN(Date.parse(candidate.receivedAt))
  );
};

const isAlertHistory = (value: unknown): value is AlertHistoryItem[] =>
  Array.isArray(value) && value.every(isAlertHistoryItem);

const normalizeAlertHistoryItem = (
  item: AlertHistoryItem,
): AlertHistoryItem => ({
  id: item.id.trim(),
  type: item.type,
  riskLevel: item.riskLevel,
  title: item.title.trim(),
  message: item.message.trim(),
  meta: item.meta?.trim(),
  receivedAt: item.receivedAt,
});

const normalizePushRiskLevel = (
  value: unknown,
): AlertHistoryRiskLevel | null | undefined => {
  if (value === null) {
    return null;
  }

  if (typeof value !== "string") {
    return undefined;
  }

  return validRiskLevels.has(value as AlertHistoryRiskLevel)
    ? (value as AlertHistoryRiskLevel)
    : undefined;
};

const stringifyMeta = (value: unknown): string | undefined => {
  if (value === undefined || value === null) {
    return undefined;
  }

  if (typeof value === "string") {
    return value;
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export function createAlertHistoryItemFromNotificationContent(
  content: NotificationContent,
): AlertHistoryItem | null {
  const data = content.data ?? {};
  const type = data.type;
  const id = data.id;
  const createdAt = data.created_at;

  if (
    typeof id !== "string" ||
    typeof type !== "string" ||
    !validAlertTypes.has(type as AlertHistoryType)
  ) {
    return null;
  }

  return {
    id,
    type: type as AlertHistoryType,
    riskLevel: normalizePushRiskLevel(data.risk_level),
    title: content.title?.trim() || "알림",
    message: content.body?.trim() || "새 알림이 도착했습니다.",
    meta: stringifyMeta(data.meta),
    receivedAt:
      typeof createdAt === "string" && !Number.isNaN(Date.parse(createdAt))
        ? createdAt
        : new Date().toISOString(),
  };
}

export const createAlertHistoryItemFromPushContent =
  createAlertHistoryItemFromNotificationContent;

export async function saveAlertHistoryItemFromNotificationContent(
  content: NotificationContent,
) {
  const item = createAlertHistoryItemFromNotificationContent(content);
  if (item) {
    await saveAlertHistoryItem(item);
  }
}

export const saveAlertHistoryItemFromPushContent =
  saveAlertHistoryItemFromNotificationContent;

const sortAlertHistory = (items: AlertHistoryItem[]) =>
  [...items].sort(
    (firstItem, secondItem) =>
      Date.parse(secondItem.receivedAt) - Date.parse(firstItem.receivedAt),
  );

export async function loadAlertHistory(): Promise<AlertHistoryItem[]> {
  try {
    if (Platform.OS === "web") {
      const saved = window.localStorage.getItem(ALERT_HISTORY_STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return isAlertHistory(parsed) ? sortAlertHistory(parsed) : [];
    }

    if (!ALERT_HISTORY_FILE_URI) {
      return [];
    }

    const fileInfo = await FileSystem.getInfoAsync(ALERT_HISTORY_FILE_URI);
    if (!fileInfo.exists) {
      return [];
    }

    const saved = await FileSystem.readAsStringAsync(ALERT_HISTORY_FILE_URI);
    const parsed = JSON.parse(saved);
    return isAlertHistory(parsed) ? sortAlertHistory(parsed) : [];
  } catch (error) {
    console.error("Failed to load alert history", error);
    return [];
  }
}

export async function saveAlertHistory(items: AlertHistoryItem[]) {
  const serializedItems = JSON.stringify(
    sortAlertHistory(items.map(normalizeAlertHistoryItem)),
  );

  if (Platform.OS === "web") {
    window.localStorage.setItem(ALERT_HISTORY_STORAGE_KEY, serializedItems);
    return;
  }

  if (!ALERT_HISTORY_FILE_URI) {
    return;
  }

  await FileSystem.writeAsStringAsync(ALERT_HISTORY_FILE_URI, serializedItems);
}

export async function saveAlertHistoryItem(item: AlertHistoryItem) {
  if (!isAlertHistoryItem(item)) {
    return;
  }

  const savedItems = await loadAlertHistory();
  const normalizedItem = normalizeAlertHistoryItem(item);
  const nextItems = [
    normalizedItem,
    ...savedItems.filter((savedItem) => savedItem.id !== normalizedItem.id),
  ];

  await saveAlertHistory(nextItems);
}

export async function clearAlertHistory() {
  if (Platform.OS === "web") {
    window.localStorage.removeItem(ALERT_HISTORY_STORAGE_KEY);
    return;
  }

  if (!ALERT_HISTORY_FILE_URI) {
    return;
  }

  const fileInfo = await FileSystem.getInfoAsync(ALERT_HISTORY_FILE_URI);
  if (fileInfo.exists) {
    await FileSystem.deleteAsync(ALERT_HISTORY_FILE_URI, { idempotent: true });
  }
}
