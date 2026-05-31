import { Stack } from "expo-router";

import { InAppNotificationProvider } from "../src/notifications/inAppNotification";

export default function RootLayout() {
  return (
    <InAppNotificationProvider>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="onboarding" />
        <Stack.Screen name="basic-info" />
        <Stack.Screen name="mobility-status" />
        <Stack.Screen name="address-settings" />
        <Stack.Screen name="permission-consent" />
        <Stack.Screen name="location-permission" />
        <Stack.Screen name="disaster-safe" options={{ animation: "none" }} />
        <Stack.Screen name="disaster-caution" options={{ animation: "none" }} />
        <Stack.Screen name="disaster-danger" options={{ animation: "none" }} />
        <Stack.Screen
          name="disaster-emergency"
          options={{ animation: "none" }}
        />
        <Stack.Screen name="alert-history" />
        <Stack.Screen name="missing" options={{ animation: "none" }} />
        <Stack.Screen name="missing-detail" />
        <Stack.Screen name="profile-edit" />
        <Stack.Screen name="profile-edit1" />
        <Stack.Screen name="shelter-route" />
        <Stack.Screen name="evacuation-complete" />
      </Stack>
    </InAppNotificationProvider>
  );
}
