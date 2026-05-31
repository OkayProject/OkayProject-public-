import { Platform } from "react-native";
import * as FileSystem from "expo-file-system/legacy";

export type AlertMethod = "voice" | "vibration" | "flash";

const ALERT_METHODS_STORAGE_KEY = "okay-alert-methods";
const DEFAULT_ALERT_METHODS: AlertMethod[] = ["vibration", "flash"];
const ALERT_METHODS_FILE_URI = FileSystem.documentDirectory
  ? `${FileSystem.documentDirectory}${ALERT_METHODS_STORAGE_KEY}.json`
  : null;

const validAlertMethods = new Set<AlertMethod>([
  "voice",
  "vibration",
  "flash",
]);

const isAlertMethods = (value: unknown): value is AlertMethod[] =>
  Array.isArray(value) &&
  value.every(
    (item) => typeof item === "string" && validAlertMethods.has(item as AlertMethod),
  );

const normalizeAlertMethods = (methods: AlertMethod[]) => {
  const uniqueMethods = methods.filter(
    (method, index) =>
      validAlertMethods.has(method) && methods.indexOf(method) === index,
  );

  return uniqueMethods.length > 0 ? uniqueMethods : DEFAULT_ALERT_METHODS;
};

export async function loadAlertMethods(): Promise<AlertMethod[]> {
  try {
    if (Platform.OS === "web") {
      const saved = window.localStorage.getItem(ALERT_METHODS_STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return isAlertMethods(parsed)
        ? normalizeAlertMethods(parsed)
        : DEFAULT_ALERT_METHODS;
    }

    if (!ALERT_METHODS_FILE_URI) {
      return DEFAULT_ALERT_METHODS;
    }

    const fileInfo = await FileSystem.getInfoAsync(ALERT_METHODS_FILE_URI);
    if (!fileInfo.exists) {
      return DEFAULT_ALERT_METHODS;
    }

    const saved = await FileSystem.readAsStringAsync(ALERT_METHODS_FILE_URI);
    const parsed = JSON.parse(saved);
    return isAlertMethods(parsed)
      ? normalizeAlertMethods(parsed)
      : DEFAULT_ALERT_METHODS;
  } catch (error) {
    console.error("Failed to load alert methods", error);
    return DEFAULT_ALERT_METHODS;
  }
}

export async function saveAlertMethods(methods: AlertMethod[]) {
  const serializedMethods = JSON.stringify(normalizeAlertMethods(methods));

  if (Platform.OS === "web") {
    window.localStorage.setItem(ALERT_METHODS_STORAGE_KEY, serializedMethods);
    return;
  }

  if (!ALERT_METHODS_FILE_URI) {
    return;
  }

  await FileSystem.writeAsStringAsync(ALERT_METHODS_FILE_URI, serializedMethods);
}
