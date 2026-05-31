import { useEffect, useRef, useState } from "react";
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

import { searchKakaoAddresses } from "../src/api/kakaoAddressApi";
import { saveUserProfile } from "../src/api/userProfileApi";
import { colors, radius, spacing, typography } from "../src/constants/theme";
import {
  AppHeader,
  AppScreen,
  FieldLabel,
  InputBox,
  MaterialFieldLabel,
  OptionPill,
  ScreenTitle,
} from "../src/components/okay-ui";
import { useAlertMethodFeedback } from "../src/hooks/useAlertMethodFeedback";
import {
  loadAlertMethods,
  saveAlertMethods,
  type AlertMethod,
} from "../src/storage/alertPreferences";
import {
  loadFrequentPlaces,
  loadSavedUserId,
  loadUserAddress,
  loadUserBasicInfo,
  loadUserMobilityInfo,
  saveFrequentPlaces,
  saveUserAddress,
  saveUserBasicInfo,
  saveUserId,
  saveUserMobilityInfo,
  type FrequentPlace,
  type UserAddress,
  validateName,
  validatePhone,
} from "../src/storage/userProfile";

type FloorOption = "basement" | "first" | "none";
type FieldName = "name" | "phone";
type AddressSearchResult = Omit<UserAddress, "floorOption">;
type SearchTarget = { type: "home" } | { type: "frequent"; index: number };

const policyTitles = [
  "서비스 이용약관",
  "개인정보 처리방침",
  "위치기반 서비스 이용약관",
] as const;

type PolicyTitle = (typeof policyTitles)[number];

const policyContents: Record<PolicyTitle, string> = {
  "서비스 이용약관": `본 약관은 아예알겠수다 팀(이하 "운영자")이 제공하는 내곁안전 서비스(이하 "서비스")의 이용과 관련하여 운영자와 이용자 간의 권리, 의무 및 책임사항을 정하는 것을 목적으로 합니다.

제1조 (서비스의 목적)
본 서비스는 이용자의 위치 및 입력 정보를 바탕으로 재난, 침수 위험 등 안전 관련 정보를 안내하기 위한 참고용 서비스입니다.
본 서비스는 재난, 사고, 범죄, 실종 등의 발생을 예방하거나 이용자의 안전을 보장하는 서비스가 아니며, 공식 기관의 신고, 구조, 대피 안내 또는 재난 대응을 대체하지 않습니다.

제2조 (서비스의 내용)
운영자는 이용자에게 다음과 같은 기능을 제공할 수 있습니다.

1. 이용자의 현재 위치 또는 설정 지역을 기반으로 한 안전 정보 안내
2. 공공데이터 및 자체 분석 결과를 활용한 침수 위험도, 위험 단계, 관련 근거 안내
3. 이용자 설정 및 상황에 따른 알림, 음성 안내 등 안전 알림 기능
4. 실종자 발견과 신고 지원을 위한 실종자 관련 정보, 사진 또는 AI 변환 이미지 안내
5. 기타 운영자가 서비스 제공을 위해 필요하다고 판단하는 부가 기능

제3조 (서비스 정보의 한계)
1. 서비스에서 제공하는 정보는 공공데이터, 기상 정보, 위치 정보, 자체 분석 결과 등을 바탕으로 생성되며, 실제 현장 상황과 차이가 있을 수 있습니다.
2. 통신 상태, 위치 정보의 정확도, 공공데이터 제공처의 갱신 주기, 시스템 처리 시간 등에 따라 정보 제공이 지연되거나 부정확할 수 있습니다.
3. 운영자는 서비스에서 제공하는 정보의 정확성, 완전성, 최신성 또는 특정 목적에의 적합성을 보장하지 않습니다.
4. 이용자는 서비스에서 제공하는 정보를 참고 자료로 활용해야 하며, 실제 위험 상황에서는 공식 기관의 안내와 현장 상황을 우선적으로 확인해야 합니다.

제4조 (이용자의 책임)
1. 이용자는 본 서비스를 자신의 판단을 보조하는 참고 자료로 이용해야 하며, 실제 상황 판단과 행동에 대한 최종 책임은 이용자 본인에게 있습니다.
2. 위급하거나 긴급한 상황이 발생한 경우 이용자는 반드시 경찰(112), 소방·구급(119), 지방자치단체, 재난안전문자 등 공식 기관의 안내와 도움을 따라야 합니다.
3. 이용자는 서비스 이용 시 정확한 정보 입력과 위치 권한 설정을 위해 노력해야 하며, 부정확한 입력 또는 권한 제한으로 인해 서비스 정보가 제한될 수 있음을 이해합니다.

제5조 (위치 정보 및 개인정보의 처리)
1. 서비스는 위치 기반 안전 정보 제공을 위해 이용자의 위치 정보 및 서비스 이용에 필요한 정보를 처리할 수 있습니다.
2. 위치 정보 및 개인정보의 수집, 이용, 보관, 파기 등에 관한 구체적인 사항은 별도의 개인정보 처리방침 및 위치기반서비스 이용약관에 따릅니다.
3. 운영자는 이용자의 위치 정보와 개인정보를 관련 법령 및 서비스 정책에 따라 보호하기 위해 노력합니다.

제6조 (서비스 제공의 변경 및 중단)
운영자는 다음 각 호의 경우 서비스의 전부 또는 일부를 변경하거나 일시적으로 중단할 수 있습니다.

1. 시스템 점검, 유지보수 또는 업데이트가 필요한 경우
2. 통신 장애, 서버 장애, 데이터 제공처의 장애가 발생한 경우
3. 공공데이터, 기상 정보, 지도 정보 등 외부 데이터 제공이 중단되거나 변경되는 경우
4. 천재지변, 재난, 정전, 기타 불가항력적인 사유가 발생한 경우
5. 서비스 운영상 필요하다고 합리적으로 판단되는 경우

제7조 (금지 행위)
이용자는 서비스 이용과 관련하여 다음 각 호의 행위를 해서는 안 됩니다.

1. 타인의 개인정보 또는 위치 정보를 무단으로 이용하는 행위
2. 허위 정보 입력, 비정상적인 접근, 서비스 오작동을 유발하는 행위
3. 서비스에서 제공하는 정보를 왜곡하거나 무단으로 복제, 배포, 상업적으로 이용하는 행위
4. 운영자, 다른 이용자 또는 제3자의 권리와 이익을 침해하는 행위
5. 서비스에서 제공되는 실종자 사진, 얼굴 이미지, AI 변환 이미지 또는 관련 정보를 실종자 발견 및 신고 지원 목적 외로 저장, 복제, 캡처, 배포, 게시, 가공, 상업적으로 이용하는 행위
6. 실종자 사진, 얼굴 이미지 또는 AI 변환 이미지를 이용하여 당사자 또는 가족의 명예, 사생활, 초상권, 개인정보 자기결정권을 침해하는 행위
7. 실종자 관련 정보를 허위 제보, 조롱, 비방, 사칭, 딥페이크 제작, AI 학습, 얼굴 인식, 신원 추적 등 서비스 목적과 무관하거나 부적절한 목적으로 이용하는 행위
8. 관련 법령 또는 본 약관을 위반하는 행위

제8조 (면책)
1. 운영자는 관련 법령이 허용하는 범위 내에서, 서비스에서 제공하는 정보의 지연, 오류, 누락 또는 이용자의 판단에 따른 행동으로 인해 발생한 손해에 대해 책임을 지지 않습니다.
2. 운영자는 공공데이터, 기상 정보, 지도 정보, 통신망 등 외부 요인으로 인해 발생한 서비스 이용 장애 또는 정보 오류에 대해 책임을 지지 않습니다.
3. 단, 운영자의 고의 또는 중대한 과실로 인해 이용자에게 손해가 발생한 경우에는 관련 법령에 따라 책임을 부담합니다.

제9조 (약관의 변경)
1. 운영자는 관련 법령을 위반하지 않는 범위에서 본 약관을 변경할 수 있습니다.
2. 약관이 변경되는 경우 운영자는 서비스 화면 또는 기타 적절한 방법을 통해 변경 내용을 안내합니다.
3. 이용자는 변경된 약관에 동의하지 않을 경우 서비스 이용을 중단할 수 있습니다.

제10조 (문의)
서비스 이용과 관련한 문의는 아래 연락처를 통해 접수할 수 있습니다.

- 이메일: 0503jyw@sookmyung.ac.kr`,
  "개인정보 처리방침": `아예알겠수다 팀(이하 "운영자")은 「개인정보 보호법」 등 관련 법령을 준수하며, 내곁안전 서비스(이하 "서비스") 이용자의 개인정보를 보호하기 위해 다음과 같이 개인정보 처리방침을 수립합니다.

1. 수집하는 개인정보 항목

운영자는 서비스 제공을 위해 다음 정보를 수집하거나 처리할 수 있습니다.

1. 이용자가 직접 입력하는 정보
- 이름
- 연락처
- 거주지 또는 설정 주소
- 자주 가는 장소
- 거주 형태 또는 층수 정보
- 이동약자 여부 등 안전 알림 제공을 위해 이용자가 입력한 프로필 정보

2. 서비스 이용 과정에서 처리되는 정보
- 현재 위치 또는 설정 위치 정보
- 알림 수신 방식 설정
- 기기 정보: 운영체제, 앱 버전 등
- 서비스 이용 중 발생하는 오류 정보 또는 접속 관련 정보

운영자는 주민등록번호, 금융정보 등 서비스 제공에 필요하지 않은 민감한 정보를 수집하지 않습니다.

2. 개인정보의 이용 목적

운영자는 수집한 개인정보를 다음 목적에 한해 이용합니다.

1. 이용자 위치 또는 설정 지역을 기반으로 한 안전 정보 제공
2. 침수 위험도, 위험 단계, 안전 알림 등 맞춤형 정보 안내
3. 이용자 특성에 따른 알림 방식 제공
4. 서비스 설정 저장 및 이용자 편의 제공
5. 서비스 오류 확인, 품질 개선 및 안정적인 운영

3. 개인정보의 보관 및 이용 기간

운영자는 개인정보를 수집 및 이용 목적이 달성될 때까지 보관하며, 목적 달성 후에는 지체 없이 파기합니다.

1. 프로필 정보: 이용자가 서비스를 이용하는 동안 보관하며, 이용자가 삭제 또는 동의 철회를 요청하는 경우 파기
2. 위치 정보: 안전 정보 제공을 위해 일시적으로 처리하며, 별도 저장이 필요한 경우 위치기반서비스 이용약관 및 관련 동의 범위에 따름
3. 오류 및 서비스 운영 정보: 서비스 품질 개선 목적 달성 후 파기

단, 관련 법령에 따라 일정 기간 보관이 필요한 경우에는 해당 법령에서 정한 기간 동안 보관할 수 있습니다.

4. 개인정보의 제3자 제공

운영자는 이용자의 개인정보를 원칙적으로 제3자에게 제공하지 않습니다.

다만, 다음의 경우에는 예외적으로 제공될 수 있습니다.

1. 이용자가 사전에 동의한 경우
2. 법령에 따라 제공 의무가 발생한 경우
3. 수사기관, 법원 등 권한 있는 기관이 법령에 따른 절차에 따라 요청한 경우

5. 개인정보 처리의 위탁

운영자는 현재 개인정보 처리를 외부 업체에 위탁하지 않습니다.

향후 서비스 운영을 위해 외부 업체에 개인정보 처리를 위탁하는 경우, 위탁받는 자, 위탁 업무의 내용, 보유 및 이용 기간 등을 서비스 화면 또는 별도 고지 방법을 통해 안내합니다.

6. 개인정보의 파기

운영자는 개인정보의 이용 목적이 달성되거나 보관 기간이 종료된 경우 지체 없이 해당 정보를 파기합니다.

전자적 파일 형태의 개인정보는 복구할 수 없는 방법으로 삭제하며, 종이 문서 형태의 개인정보가 있는 경우 분쇄 또는 소각 등의 방법으로 파기합니다.

7. 이용자의 권리

이용자는 언제든지 자신의 개인정보에 대해 열람, 정정, 삭제, 처리정지를 요청할 수 있습니다.

이용자는 서비스 이용을 중단하거나 개인정보 처리에 대한 동의를 철회할 수 있으며, 이 경우 서비스의 일부 또는 전부 이용이 제한될 수 있습니다.

8. 개인정보 보호를 위한 조치

운영자는 이용자의 개인정보가 분실, 도난, 유출, 위조, 변조 또는 훼손되지 않도록 필요한 보호 조치를 위해 노력합니다.

또한 위치 정보, 주소, 이동약자 여부 등 안전 알림 제공에 필요한 정보는 민감하게 취급하며, 서비스 제공 목적 외로 사용하지 않습니다.

9. 개인정보 처리방침의 변경

운영자는 관련 법령, 서비스 내용 또는 운영 정책의 변경에 따라 본 개인정보 처리방침을 변경할 수 있습니다.

개인정보 처리방침이 변경되는 경우 서비스 화면 또는 기타 적절한 방법을 통해 변경 내용을 안내합니다.

10. 개인정보 보호 문의

개인정보 처리와 관련한 문의는 아래 연락처를 통해 접수할 수 있습니다.

- 이메일: 0503jyw@sookmyung.ac.kr`,
  "위치기반 서비스 이용약관": `본 약관은 아예알겠수다 팀(이하 "운영자")이 제공하는 내곁안전 서비스(이하 "서비스")에서 위치정보를 이용하는 것과 관련하여 운영자와 이용자 간의 권리, 의무 및 책임사항을 정하는 것을 목적으로 합니다.

제1조 (위치정보의 이용 목적)
운영자는 이용자의 현재 위치 또는 이용자가 설정한 위치를 기반으로 재난, 침수 위험 등 안전 관련 정보를 안내하기 위해 위치정보를 이용합니다.
위치정보는 안전 정보 제공, 위험 알림, 주변 안전 정보 안내 등 서비스 제공 목적 범위 내에서만 이용됩니다.

제2조 (위치정보의 수집 및 이용)
1. 서비스는 이용자의 동의를 받은 경우에 한하여 현재 위치 또는 설정 위치 정보를 수집하거나 이용할 수 있습니다.
2. 위치정보는 서비스 이용 중 안전 정보 제공을 위해 일시적으로 처리될 수 있습니다.
3. 운영자는 위치정보를 서비스 제공 목적과 무관하게 이용하지 않습니다.
4. 위치정보의 정확도는 기기 상태, GPS 수신 상태, 통신 환경, 운영체제 설정 등에 따라 달라질 수 있습니다.

제3조 (위치정보의 보관 및 파기)
1. 운영자는 위치정보의 이용 목적이 달성된 경우 개인위치정보를 지체 없이 파기합니다.
2. 단, 관련 법령에 따라 위치정보 수집, 이용 또는 제공 사실 확인자료를 보관해야 하는 경우에는 해당 법령에서 정한 기간 동안 보관할 수 있습니다.
3. 서비스 품질 개선이나 오류 확인을 위해 필요한 경우에도 개인을 식별할 수 없도록 처리된 정보만 제한적으로 활용할 수 있습니다.

제4조 (위치정보의 제3자 제공)
운영자는 이용자의 개인위치정보를 원칙적으로 제3자에게 제공하지 않습니다.

다만, 다음의 경우에는 예외적으로 제공될 수 있습니다.

1. 이용자가 사전에 동의한 경우
2. 법령에 따라 제공 의무가 발생한 경우
3. 수사기관, 법원 등 권한 있는 기관이 법령에 따른 절차에 따라 요청한 경우

제5조 (이용자의 권리)
1. 이용자는 언제든지 위치정보 수집 및 이용에 대한 동의의 전부 또는 일부를 철회할 수 있습니다.
2. 이용자는 자신의 위치정보 이용 내역에 대해 열람, 고지, 정정 또는 삭제를 요청할 수 있습니다.
3. 이용자가 위치정보 이용에 대한 동의를 철회하거나 기기에서 위치 권한을 제한하는 경우, 위치 기반 안전 정보 제공 등 서비스의 일부 또는 전부 이용이 제한될 수 있습니다.

제6조 (서비스 정보의 한계)
1. 서비스에서 제공하는 위치 기반 안전 정보는 공공데이터, 기상 정보, 지도 정보, 위치 정보 등을 바탕으로 한 참고용 정보입니다.
2. 위치정보의 오차, 통신 지연, 공공데이터 갱신 지연, 기기 설정 등의 사유로 실제 현장 상황과 서비스 안내 내용이 다를 수 있습니다.
3. 서비스는 긴급 구조, 신고, 대피 안내 또는 공식 재난 대응을 대체하지 않습니다.
4. 위급하거나 긴급한 상황에서는 반드시 경찰(112), 소방·구급(119), 지방자치단체 등 공식 기관의 안내와 도움을 따라야 합니다.

제7조 (면책)
1. 운영자는 관련 법령이 허용하는 범위 내에서, 위치정보의 오차, 통신 장애, 외부 데이터 오류 또는 이용자의 판단에 따른 행동으로 인해 발생한 손해에 대해 책임을 지지 않습니다.
2. 단, 운영자의 고의 또는 중대한 과실로 인해 이용자에게 손해가 발생한 경우에는 관련 법령에 따라 책임을 부담합니다.

제8조 (약관의 변경)
1. 운영자는 관련 법령을 위반하지 않는 범위에서 본 약관을 변경할 수 있습니다.
2. 약관이 변경되는 경우 서비스 화면 또는 기타 적절한 방법을 통해 변경 내용을 안내합니다.
3. 이용자는 변경된 약관에 동의하지 않을 경우 서비스 이용을 중단할 수 있습니다.

제9조 (문의)
위치기반 서비스 이용과 관련한 문의는 아래 연락처를 통해 접수할 수 있습니다.

- 이메일: 0503jyw@sookmyung.ac.kr`,
};

export default function ProfileEditScreen() {
  const nameInputRef = useRef<TextInput>(null);
  const phoneInputRef = useRef<TextInput>(null);
  const { playAlertMethodFeedback, flashPreview } = useAlertMethodFeedback();
  const [modalTitle, setModalTitle] = useState<PolicyTitle | null>(null);
  const [isAddressSearchOpen, setIsAddressSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AddressSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchTarget, setSearchTarget] = useState<SearchTarget>({
    type: "home",
  });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [loadedBasicInfo, setLoadedBasicInfo] = useState(false);
  const [touched, setTouched] = useState<Record<FieldName, boolean>>({
    name: false,
    phone: false,
  });
  const [alarmMethods, setAlarmMethods] = useState<AlertMethod[]>([
    "vibration",
    "flash",
  ]);
  const [userAddress, setUserAddress] = useState<UserAddress | null>(null);
  const [frequentPlaces, setFrequentPlaces] = useState<FrequentPlace[]>([]);
  const [floorOption, setFloorOption] = useState<FloorOption>("basement");
  const [saveMessage, setSaveMessage] = useState("");
  const [saveError, setSaveError] = useState("");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const nameError = touched.name ? validateName(name) : "";
  const phoneError = touched.phone ? validatePhone(phone) : "";
  const displayAddress =
    userAddress?.name ||
    userAddress?.roadAddressName ||
    userAddress?.addressName ||
    "용산구 효창공원로86길 33";

  useEffect(() => {
    let isMounted = true;

    const loadSavedProfile = async () => {
      const [savedBasicInfo, savedAddress, savedFrequentPlaces, savedAlertMethods] =
        await Promise.all([
          loadUserBasicInfo(),
          loadUserAddress(),
          loadFrequentPlaces(),
          loadAlertMethods(),
        ]);

      if (!isMounted) {
        return;
      }

      if (savedBasicInfo) {
        setName(savedBasicInfo.name);
        setPhone(savedBasicInfo.phone);
      }

      if (savedAddress) {
        setUserAddress(savedAddress);

        if (savedAddress.floorOption) {
          setFloorOption(savedAddress.floorOption);
        }
      }

      setFrequentPlaces(savedFrequentPlaces);
      setAlarmMethods(savedAlertMethods);

      setLoadedBasicInfo(true);
    };

    void loadSavedProfile();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!loadedBasicInfo || validateName(name) || validatePhone(phone)) {
      return;
    }

    void saveUserBasicInfo({ name, phone }).catch((error) => {
      console.error("Failed to save user basic info", error);
    });
  }, [loadedBasicInfo, name, phone]);

  const markTouched = (fieldName: FieldName) => {
    setTouched((current) => ({
      ...current,
      [fieldName]: true,
    }));
  };

  const toggleAlarmMethod = (method: AlertMethod) => {
    const isSelecting = !alarmMethods.includes(method);

    setAlarmMethods((current) => {
      const nextMethods = current.includes(method)
        ? current.filter((item) => item !== method)
        : [...current, method];

      void saveAlertMethods(nextMethods).catch((error) => {
        console.error("Failed to save alert methods", error);
      });

      return nextMethods;
    });

    if (isSelecting) {
      void playAlertMethodFeedback(method);
    }
  };

  const handleFloorOptionChange = (nextFloorOption: FloorOption) => {
    setFloorOption(nextFloorOption);

    if (userAddress) {
      const nextAddress = {
        ...userAddress,
        floorOption: nextFloorOption,
      };

      setUserAddress(nextAddress);
      void saveUserAddress(nextAddress).catch((error) => {
        console.error("Failed to save address", error);
      });
    }
  };

  const openAddressSearch = (target: SearchTarget) => {
    setSearchTarget(target);
    setSearchQuery("");
    setSearchResults([]);
    setSearchError("");
    setIsAddressSearchOpen(true);
  };

  const handleAddressSearch = async () => {
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

  const handleSelectAddress = async (address: AddressSearchResult) => {
    setIsAddressSearchOpen(false);
    setSearchQuery("");
    setSearchResults([]);
    setSearchError("");

    if (searchTarget.type === "home") {
      const nextAddress: UserAddress = {
        ...address,
        floorOption,
      };

      setUserAddress(nextAddress);
      await saveUserAddress(nextAddress);
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

  const handleSaveProfile = async () => {
    setTouched({ name: true, phone: true });
    setSaveMessage("");
    setSaveError("");

    const nextNameError = validateName(name);
    const nextPhoneError = validatePhone(phone);

    if (nextNameError || nextPhoneError) {
      setSaveError("이름과 전화번호를 올바르게 입력해 주세요.");
      return;
    }

    if (!userAddress) {
      setSaveError("집 주소를 선택해 주세요.");
      return;
    }

    if (alarmMethods.length === 0) {
      setSaveError("주요 알림 방식을 하나 이상 선택해 주세요.");
      return;
    }

    setIsSavingProfile(true);

    try {
      const [savedUserId, mobilityInfo] = await Promise.all([
        loadSavedUserId(),
        loadUserMobilityInfo(),
      ]);
      const homeAddress = userAddress.roadAddressName || userAddress.addressName;
      const nextMobilityInfo = {
        isMobilityVulnerable: mobilityInfo?.isMobilityVulnerable ?? false,
        mobilityType: mobilityInfo?.mobilityType ?? null,
        alarmMethods,
      };

      await Promise.all([
        saveUserBasicInfo({ name, phone }),
        saveUserAddress({ ...userAddress, floorOption }),
        saveFrequentPlaces(frequentPlaces),
        saveAlertMethods(alarmMethods),
        saveUserMobilityInfo(nextMobilityInfo),
      ]);

      const response = await saveUserProfile({
        user_id: savedUserId,
        name,
        phone,
        address: homeAddress,
        home_latitude: Number(userAddress.y),
        home_longitude: Number(userAddress.x),
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
          nextMobilityInfo.mobilityType === "elderly" ||
          nextMobilityInfo.mobilityType === "hearing" ||
          nextMobilityInfo.mobilityType === "visual",
        disability_type: nextMobilityInfo.mobilityType,
        is_mobility_vulnerable: nextMobilityInfo.isMobilityVulnerable,
        is_semi_basement_resident: floorOption === "basement",
        notification_enabled: alarmMethods.length > 0,
        notification_methods: alarmMethods,
      });

      await saveUserId(response.user_id);
      setSaveMessage("수정한 정보가 저장되었습니다.");
    } catch (error) {
      console.error("Failed to update user profile", error);
      setSaveError("수정한 정보를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setIsSavingProfile(false);
    }
  };

  return (
    <AppScreen>
      {flashPreview}
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 12 : 0}
        style={styles.keyboardView}
      >
        <AppHeader title="정보 수정" showBack />
        <ScrollView showsVerticalScrollIndicator={false} bounces={false}>
          <ScreenTitle>사용자 기본 정보</ScreenTitle>
          <View style={styles.section}>
            <View>
              <FieldLabel icon="person-outline">이름</FieldLabel>
              <TextInput
                ref={nameInputRef}
                accessibilityLabel="이름 수정"
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
                accessibilityLabel="전화번호 수정"
                enterKeyHint="done"
                keyboardType="phone-pad"
                onBlur={() => markTouched("phone")}
                onChangeText={setPhone}
                onFocus={() => markTouched("phone")}
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
            <View>
              <FieldLabel icon="notifications-outline">
                주요 알림 방식
              </FieldLabel>
              <View style={styles.row}>
                <OptionPill
                  selected={alarmMethods.includes("voice")}
                  onPress={() => toggleAlarmMethod("voice")}
                >
                  음성
                </OptionPill>
                <OptionPill
                  selected={alarmMethods.includes("vibration")}
                  onPress={() => toggleAlarmMethod("vibration")}
                >
                  진동
                </OptionPill>
                <OptionPill
                  selected={alarmMethods.includes("flash")}
                  onPress={() => toggleAlarmMethod("flash")}
                >
                  플래시
                </OptionPill>
              </View>
            </View>
          </View>

          <ScreenTitle>주소 및 생활권 설정</ScreenTitle>
          <View style={styles.section}>
            <View>
              <MaterialFieldLabel icon="home-outline">집</MaterialFieldLabel>
              <InputBox
                value={displayAddress}
                onPress={() => openAddressSearch({ type: "home" })}
              />
            </View>
            <View>
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
                *내 위치의 침수 위험을 더 정확히 계산하기 위해 사용돼요.
              </Text>
            </View>
            <View>
              <View style={styles.placeHeader}>
                <MaterialFieldLabel icon="office-building-outline">
                  자주 가는 장소
                </MaterialFieldLabel>
                <Text style={styles.helper}>
                  *최대 3개까지 등록할 수 있습니다.
                </Text>
              </View>
              <View style={styles.placeInputs}>
                {frequentPlaces.length === 0 ? (
                  <InputBox
                    placeholder="+ 장소 추가"
                    onPress={() =>
                      openAddressSearch({ type: "frequent", index: 0 })
                    }
                  />
                ) : (
                  <>
                    {frequentPlaces.map((place, index) => (
                      <InputBox
                        key={`${place.x}-${place.y}-${index}`}
                        value={place.name || place.roadAddressName || place.addressName}
                        onPress={() =>
                          openAddressSearch({ type: "frequent", index })
                        }
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
                            <Ionicons
                              name="remove"
                              size={22}
                              color={colors.primary}
                            />
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
                  </>
                )}
              </View>
            </View>
          </View>

          <View style={styles.saveArea}>
            {saveError ? <Text style={styles.errorText}>{saveError}</Text> : null}
            {saveMessage ? (
              <Text style={styles.successText}>{saveMessage}</Text>
            ) : null}
            <Pressable
              accessibilityRole="button"
              onPress={isSavingProfile ? undefined : () => void handleSaveProfile()}
              style={({ pressed }) => [
                styles.saveButton,
                pressed && styles.pressed,
                isSavingProfile && styles.disabledButton,
              ]}
            >
              <Text style={styles.saveButtonText}>
                {isSavingProfile ? "저장 중..." : "수정 완료"}
              </Text>
            </Pressable>
          </View>

          <Text style={styles.policyTitle}>약관 및 정책</Text>
          <View style={styles.policyList}>
            {policyTitles.map((title) => (
              <Pressable
                key={title}
                accessibilityRole="button"
                onPress={() => setModalTitle(title)}
                style={({ pressed }) => [
                  styles.policyButton,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.policyText}>{title}</Text>
                <Ionicons
                  name="chevron-forward"
                  size={30}
                  color={colors.text}
                />
              </Pressable>
            ))}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>

      <Modal
        transparent
        visible={modalTitle !== null}
        animationType="fade"
        onRequestClose={() => setModalTitle(null)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalBox}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{modalTitle}</Text>
              <Pressable
                onPress={() => setModalTitle(null)}
                accessibilityRole="button"
              >
                <Ionicons name="close" size={26} color={colors.text} />
              </Pressable>
            </View>
            <ScrollView
              showsVerticalScrollIndicator
              style={styles.modalScroll}
              contentContainerStyle={styles.modalContent}
            >
              <Text style={styles.modalContentText}>
                {modalTitle ? policyContents[modalTitle] : ""}
              </Text>
            </ScrollView>
          </View>
        </View>
      </Modal>

      <Modal
        animationType="slide"
        onRequestClose={() => setIsAddressSearchOpen(false)}
        transparent
        visible={isAddressSearchOpen}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          style={styles.addressModalKeyboardView}
        >
          <View style={styles.addressModalBackdrop}>
            <View style={styles.addressModalBox}>
              <View style={styles.addressModalHeader}>
                <Text style={styles.addressModalTitle}>주소 검색</Text>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => setIsAddressSearchOpen(false)}
                >
                  <Text style={styles.addressCloseText}>닫기</Text>
                </Pressable>
              </View>

              <View style={styles.addressSearchRow}>
                <TextInput
                  autoCapitalize="none"
                  autoCorrect={false}
                  enterKeyHint="search"
                  onChangeText={setSearchQuery}
                  onSubmitEditing={() => void handleAddressSearch()}
                  placeholder="도로명 또는 지번 주소"
                  placeholderTextColor={colors.subText}
                  returnKeyType="search"
                  style={styles.addressSearchInput}
                  value={searchQuery}
                />
                <Pressable
                  accessibilityRole="button"
                  onPress={() => void handleAddressSearch()}
                  style={({ pressed }) => [
                    styles.addressSearchButton,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.addressSearchButtonText}>검색</Text>
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
                style={styles.addressResultList}
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
                        styles.addressResultItem,
                        pressed && styles.pressed,
                      ]}
                    >
                      <Text style={styles.addressResultAddress}>
                        {resultTitle}
                      </Text>
                      {resultAddress && resultAddress !== resultTitle ? (
                        <Text style={styles.addressResultSubAddress}>
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
  keyboardView: {
    flex: 1,
  },
  section: {
    marginTop: 28,
    marginBottom: 50,
    gap: 22,
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
  placeHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  placeInputs: {
    gap: spacing.md,
  },
  removePlaceButton: {
    width: 32,
    height: 32,
    marginLeft: spacing.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  saveArea: {
    gap: spacing.sm,
    marginBottom: 24,
  },
  saveButton: {
    minHeight: 48,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
  },
  disabledButton: {
    opacity: 0.6,
  },
  saveButtonText: {
    ...typography.titleMedium,
    color: colors.background,
    fontWeight: "700",
  },
  successText: {
    ...typography.helperTiny,
    color: colors.primary,
    marginBottom: 2,
  },
  policyTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
    marginBottom: 10,
  },
  policyList: {
    gap: spacing.md,
    paddingBottom: 20,
  },
  policyButton: {
    minHeight: 46,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: colors.cardLine,
    backgroundColor: colors.background,
    paddingLeft: 25,
    paddingRight: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    shadowColor: "#000",
    shadowOpacity: 0.14,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  policyText: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  pressed: {
    opacity: 0.8,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.25)",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 65,
  },
  modalBox: {
    width: "100%",
    height: 538,
    borderRadius: 26,
    backgroundColor: colors.background,
    paddingHorizontal: 24,
    paddingTop: 20,
  },
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  modalTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  modalScroll: {
    marginTop: spacing.lg,
  },
  modalContent: {
    paddingBottom: 28,
  },
  modalContentText: {
    ...typography.bodyMediumRegular,
    color: colors.text,
    lineHeight: 23,
  },
  addressModalKeyboardView: {
    flex: 1,
  },
  addressModalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.25)",
    justifyContent: "flex-start",
    paddingTop: Platform.select({ ios: 225, default: 185 }),
    paddingHorizontal: spacing.lg,
  },
  addressModalBox: {
    maxHeight: "58%",
    borderRadius: 20,
    backgroundColor: colors.background,
    padding: spacing.lg,
  },
  addressModalHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  addressModalTitle: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  addressCloseText: {
    ...typography.titleMedium,
    color: colors.primary,
    fontWeight: "700",
  },
  addressSearchRow: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  addressSearchInput: {
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
  addressSearchButton: {
    minHeight: 44,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  addressSearchButtonText: {
    ...typography.titleMedium,
    color: colors.background,
    fontWeight: "700",
  },
  loader: {
    marginTop: spacing.lg,
  },
  addressResultList: {
    marginTop: spacing.md,
  },
  addressResultItem: {
    borderBottomWidth: 1,
    borderBottomColor: colors.cardLine,
    paddingVertical: spacing.md,
  },
  addressResultAddress: {
    ...typography.titleMedium,
    color: colors.text,
    fontWeight: "700",
  },
  addressResultSubAddress: {
    ...typography.helperTiny,
    color: colors.subText,
    marginTop: 4,
  },
});
