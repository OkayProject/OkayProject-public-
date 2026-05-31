// frontend/src/constants/typography.ts

export const typography = {
  // 가장 많이 쓰이는 화면 상단 제목, 버튼, 기본 중간 굵기 텍스트
  labelSmall: {
    fontSize: 11,
    lineHeight: 13,
    fontWeight: "500" as const,
  },

  // 화면의 큰 제목
  titleMedium: {
    fontSize: 16,
    lineHeight: 19,
    fontWeight: "600" as const,
  },

  // 일반 본문
  bodySmall: {
    fontSize: 11,
    lineHeight: 13,
    fontWeight: "400" as const,
  },

  // 중간 굵기 본문
  bodySmallMedium: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "500" as const,
  },

  // 입력 박스 안 기본 글씨
  inputSmall: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "400" as const,
  },

  // 선택된 입력 박스 글씨
  inputSmallBold: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "700" as const,
  },

  // 이전 버튼 옆 작은 글씨
  backSmall: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "500" as const,
  },

  // 추가 설명 문구
  helperTiny: {
    fontSize: 12,
    lineHeight: 16,
    fontWeight: "400" as const,
  },

  // 약관/동의 항목 제목
  agreementTitle: {
    fontSize: 11,
    lineHeight: 13,
    fontWeight: "600" as const,
  },

  // 약관/동의 항목 설명
  agreementBody: {
    fontSize: 9,
    lineHeight: 13,
    fontWeight: "400" as const,
  },

  // 하단 메뉴 글씨
  menuTiny: {
    fontSize: 8,
    lineHeight: 10,
    fontWeight: "500" as const,
  },

  // 실종자 카드 보조 정보
  metaSmall: {
    fontSize: 9,
    lineHeight: 15,
    fontWeight: "500" as const,
  },

  // 알람 내역, 대피소 안내의 아주 작은 본문
  tinyMedium: {
    fontSize: 7,
    lineHeight: 8,
    fontWeight: "500" as const,
  },

  // 스플래시 화면 앱 이름
  splashTitle: {
    fontSize: 28,
    lineHeight: 34,
    fontWeight: "600" as const,
  },

  // 재난 위험도 점수 숫자
  riskScore: {
    fontSize: 40,
    lineHeight: 48,
    fontWeight: "700" as const,
  },

  // 재난 위험도 점수의 “점” 글자
  riskScoreUnit: {
    fontSize: 15,
    lineHeight: 18,
    fontWeight: "500" as const,
  },

  // 재난 행동 안내 박스 제목
  guideTitle: {
    fontSize: 13,
    lineHeight: 16,
    fontWeight: "700" as const,
  },

  // 대피소 위치 확인 버튼
  shelterButton: {
    fontSize: 13,
    lineHeight: 16,
    fontWeight: "500" as const,
  },

  // 긴급 화면의 큰 대피 버튼
  emergencyButton: {
    fontSize: 24,
    lineHeight: 29,
    fontWeight: "700" as const,
  },

  // 대피소 이름
  shelterName: {
    fontSize: 11,
    lineHeight: 13,
    fontWeight: "700" as const,
  },

  // 도착/대피 완료 관련 작은 강조 글씨
  arriveText: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "700" as const,
  },

  // 대피 완료 화면 체크 문구
  completeCheck: {
    fontSize: 24,
    lineHeight: 29,
    fontWeight: "700" as const,
  },

  // 대피 완료 화면 본문
  bodyMediumRegular: {
    fontSize: 13,
    lineHeight: 16,
    fontWeight: "400" as const,
  },

  // 알람 배너 제목
  bannerTitle: {
    fontSize: 18,
    lineHeight: 22,
    fontWeight: "500" as const,
  },

  // 알람 배너 강조 문구
  bannerContentBold: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "700" as const,
  },

  // 알람 배너 일반 문구
  bannerContent: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "500" as const,
  },

  // 알람 배너 시간
  bannerTime: {
    fontSize: 9,
    lineHeight: 11,
    fontWeight: "400" as const,
  },

  // 알람 배너 버튼
  bannerButton: {
    fontSize: 10,
    lineHeight: 12,
    fontWeight: "400" as const,
  },
} as const;
