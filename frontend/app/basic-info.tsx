/*
사용자 이름/전화번호 입력받는 화면

1. 이름과 전화번호 저장
2.사용자가 입력칸을 누르면 TextInput 이 활성화되고 키보드 올라옴
3. 입력하거나 다음 버튼을 누르면 유효성 검사
4.값이 올바르면 /mobility-status 화면으로 이동
*/

import { useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useRouter } from "expo-router";

import { colors, radius, spacing, typography } from "../src/constants/theme";
import {
  AppHeader,
  AppScreen,
  FieldLabel,
  PrimaryButton,
  ScreenTitle,
} from "../src/components/okay-ui";
import {
  saveUserBasicInfo,
  validateName,
  validatePhone,
} from "../src/storage/userProfile";

type FieldName = "name" | "phone";

export default function BasicInfoScreen() {
  const router = useRouter();
  const nameInputRef = useRef<TextInput>(null);
  const phoneInputRef = useRef<TextInput>(null);
  const [name, setName] = useState(""); //이름 입력값, setName이 이름 값 바꾸는 함수
  const [phone, setPhone] = useState(""); //전화번호 입력값
  const [touched, setTouched] = useState<Record<FieldName, boolean>>({
    //사용자가 입력칸을 한 번이라도 건들였는지 저장
    name: false,
    phone: false,
  });

  //입력칸을 건들었는지 검사
  const nameError = touched.name ? validateName(name) : "";
  const phoneError = touched.phone ? validatePhone(phone) : "";

  const markTouched = (fieldName: FieldName) => {
    setTouched((current) => ({
      ...current,
      [fieldName]: true,
    }));
  };

  // 다음 버튼으로 다음 화면 이동
  const handleNext = async () => {
    const nextTouched = {
      //이름, 전화번호 유효성 검사
      name: true,
      phone: true,
    };

    setTouched(nextTouched);

    if (validateName(name) || validatePhone(phone)) {
      return;
    }

    await saveUserBasicInfo({ name, phone });
    router.push("/mobility-status" as never);
  };

  return (
    <AppScreen>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 12 : 0}
        style={styles.keyboardView}
      >
        <AppHeader title="기본 정보 입력" />
        <ScreenTitle>사용자 기본 정보</ScreenTitle>

        <View style={styles.form}>
          <View>
            <FieldLabel icon="person-outline">이름</FieldLabel>
            <TextInput
              ref={nameInputRef}
              accessibilityLabel="이름 입력"
              autoCapitalize="none"
              autoCorrect={false}
              enterKeyHint="next"
              onBlur={() => markTouched("name")}
              onChangeText={setName}
              onFocus={() => markTouched("name")}
              onSubmitEditing={() => phoneInputRef.current?.focus()}
              placeholder="이름을 입력하세요."
              placeholderTextColor={colors.subText}
              returnKeyType="next"
              style={[styles.input, nameError && styles.inputError]}
              textContentType="name"
              value={name}
            />
            {nameError ? (
              <Text style={styles.errorText}>{nameError}</Text>
            ) : null}
          </View>
          <View>
            <FieldLabel icon="call-outline">전화번호</FieldLabel>
            <TextInput
              ref={phoneInputRef}
              accessibilityLabel="전화번호 입력"
              enterKeyHint="done"
              keyboardType="phone-pad"
              onBlur={() => markTouched("phone")}
              onChangeText={setPhone}
              onFocus={() => markTouched("phone")}
              onSubmitEditing={() => void handleNext()}
              placeholder="전화번호를 입력하세요."
              placeholderTextColor={colors.subText}
              returnKeyType="done"
              style={[styles.input, phoneError && styles.inputError]}
              textContentType="telephoneNumber"
              value={phone}
            />
            {phoneError ? (
              <Text style={styles.errorText}>{phoneError}</Text>
            ) : null}
          </View>
        </View>

        <View style={styles.footer}>
          <PrimaryButton onPress={() => void handleNext()}>다음</PrimaryButton>
        </View>
      </KeyboardAvoidingView>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  keyboardView: {
    flex: 1,
  },
  form: {
    marginTop: 18,
    gap: 40,
  },
  input: {
    minHeight: 44,
    borderWidth: 1,
    borderColor: colors.cardLine,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.card,
    paddingHorizontal: spacing.lg,
    justifyContent: "center",
    ...typography.titleMedium,
    color: colors.text,
  },
  inputError: {
    borderColor: "#D92D20",
  },
  errorText: {
    ...typography.helperTiny,
    color: "#D92D20",
    marginTop: 8,
  },
  footer: {
    flex: 1,
    justifyContent: "flex-end",
  },
});
