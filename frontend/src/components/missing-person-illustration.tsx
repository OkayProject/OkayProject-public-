import { StyleSheet, View } from "react-native";

import { colors } from "../constants/theme";

export function MissingPersonIllustration({ large = false }: { large?: boolean }) {
  return (
    <View style={[styles.wrap, large && styles.wrapLarge]}>
      <View style={[styles.shadow, large && styles.shadowLarge]} />
      <View style={[styles.hair, large && styles.hairLarge]} />
      <View style={[styles.face, large && styles.faceLarge]}>
        <View style={[styles.glasses, large && styles.glassesLarge]}>
          <View style={styles.lens} />
          <View style={styles.bridge} />
          <View style={styles.lens} />
        </View>
      </View>
      <View style={[styles.neck, large && styles.neckLarge]} />
      <View style={[styles.body, large && styles.bodyLarge]}>
        <View style={[styles.lanyardLeft, large && styles.lanyardLarge]} />
        <View style={[styles.lanyardRight, large && styles.lanyardLarge]} />
        <View style={[styles.nameTag, large && styles.nameTagLarge]} />
      </View>
      <View style={[styles.armLeft, large && styles.armLarge]} />
      <View style={[styles.armRight, large && styles.armLarge]} />
      <View style={[styles.legLeft, large && styles.legLarge]} />
      <View style={[styles.legRight, large && styles.legLarge]} />
      <View style={[styles.shoeLeft, large && styles.shoeLarge]} />
      <View style={[styles.shoeRight, large && styles.shoeLarge]} />
    </View>
  );
}

const skin = "#F3C9A7";
const hair = "#5B514C";
const pants = "#547899";
const shoe = "#E8B239";

const styles = StyleSheet.create({
  wrap: {
    width: 178,
    height: 415,
    alignItems: "center",
    position: "relative",
  },
  wrapLarge: {
    width: 312,
    height: 685,
  },
  shadow: {
    position: "absolute",
    bottom: 0,
    width: 146,
    height: 23,
    borderRadius: 80,
    backgroundColor: "#E9E9E9",
  },
  shadowLarge: {
    width: 260,
    height: 34,
  },
  hair: {
    position: "absolute",
    top: 0,
    width: 90,
    height: 116,
    borderRadius: 45,
    backgroundColor: hair,
  },
  hairLarge: {
    width: 156,
    height: 196,
    borderRadius: 78,
  },
  face: {
    position: "absolute",
    top: 21,
    width: 70,
    height: 84,
    borderRadius: 35,
    backgroundColor: skin,
    alignItems: "center",
    justifyContent: "center",
  },
  faceLarge: {
    top: 42,
    width: 122,
    height: 144,
    borderRadius: 61,
  },
  glasses: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    marginTop: -8,
  },
  glassesLarge: {
    transform: [{ scale: 1.7 }],
  },
  lens: {
    width: 20,
    height: 17,
    borderWidth: 3,
    borderColor: "#333",
    borderRadius: 5,
    backgroundColor: "transparent",
  },
  bridge: {
    width: 7,
    height: 3,
    backgroundColor: "#333",
  },
  neck: {
    position: "absolute",
    top: 99,
    width: 23,
    height: 25,
    backgroundColor: skin,
  },
  neckLarge: {
    top: 175,
    width: 40,
    height: 40,
  },
  body: {
    position: "absolute",
    top: 116,
    width: 111,
    height: 145,
    borderTopLeftRadius: 32,
    borderTopRightRadius: 32,
    backgroundColor: "#F9F9F9",
    borderWidth: 1,
    borderColor: "#E2E2E2",
    overflow: "hidden",
  },
  bodyLarge: {
    top: 205,
    width: 190,
    height: 238,
    borderTopLeftRadius: 50,
    borderTopRightRadius: 50,
  },
  lanyardLeft: {
    position: "absolute",
    top: 10,
    left: 45,
    width: 2,
    height: 62,
    backgroundColor: colors.primary,
    transform: [{ rotate: "-17deg" }],
  },
  lanyardRight: {
    position: "absolute",
    top: 10,
    right: 45,
    width: 2,
    height: 62,
    backgroundColor: colors.primary,
    transform: [{ rotate: "17deg" }],
  },
  lanyardLarge: {
    top: 12,
    height: 105,
    width: 3,
  },
  nameTag: {
    position: "absolute",
    top: 67,
    alignSelf: "center",
    width: 39,
    height: 29,
    borderWidth: 4,
    borderColor: "#B84E43",
    backgroundColor: "#fff",
  },
  nameTagLarge: {
    top: 112,
    width: 68,
    height: 45,
  },
  armLeft: {
    position: "absolute",
    top: 142,
    left: 20,
    width: 21,
    height: 140,
    borderRadius: 12,
    backgroundColor: skin,
  },
  armRight: {
    position: "absolute",
    top: 142,
    right: 20,
    width: 21,
    height: 140,
    borderRadius: 12,
    backgroundColor: skin,
  },
  armLarge: {
    top: 246,
    width: 35,
    height: 232,
    borderRadius: 20,
  },
  legLeft: {
    position: "absolute",
    top: 247,
    left: 55,
    width: 38,
    height: 140,
    backgroundColor: pants,
  },
  legRight: {
    position: "absolute",
    top: 247,
    right: 55,
    width: 38,
    height: 140,
    backgroundColor: pants,
  },
  legLarge: {
    top: 424,
    width: 62,
    height: 230,
  },
  shoeLeft: {
    position: "absolute",
    bottom: 14,
    left: 46,
    width: 54,
    height: 28,
    borderRadius: 15,
    backgroundColor: shoe,
    borderWidth: 2,
    borderColor: "#fff",
    transform: [{ rotate: "7deg" }],
  },
  shoeRight: {
    position: "absolute",
    bottom: 14,
    right: 46,
    width: 54,
    height: 28,
    borderRadius: 15,
    backgroundColor: shoe,
    borderWidth: 2,
    borderColor: "#fff",
    transform: [{ rotate: "-7deg" }],
  },
  shoeLarge: {
    bottom: 20,
    width: 90,
    height: 45,
    borderRadius: 24,
  },
});
