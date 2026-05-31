export const spacing = {
  //기본 간격
  xs: 4, //아주 작은 간격
  sm: 5, //작은 간격 - 기본 버튼 마다의 간격
  md: 8, //기본 간격
  lg: 17, //큰 간격
  xl: 31, //아주 큰 간격-최근 30일 위 아래 박스사이 간격/사용자 정보 수정 전화번호 위아래, 주요 알림 방식 위아래 박스 사이 간격
} as const;

export const layout = {
  screenHorizontal: 18, //화면 양 옆 여백
  //policyBoxHorizontal: 35 //약관 및 정책 자세히 보기 박스 양옆 여백
  screenTop: 45, //화면 상단 여백
  screeBottom: 17, //화면 하단 여백
} as const;

export const size = {
  // 카드/버튼
  redButtonHeight: 33, //온보딩~위치권한의 빨강버튼 높이/대피소 위치 확인 버튼 높이
  grayButtonHeight: 28, //기본 정보 입력 시 회색버튼 높이
  scoreBoxHeight: 171, //위험도 단계 박스 높이
  menuButtonHeight: 45, //홈 하단 메뉴 버튼 높이
  actBoxHeight: 209, //주의, 위험 단계 행동요령 박스 높이
  //ActBoxHeight: 156, 긴급 단계 행동 요령 박스 높이
  //redbuttonHeight: 87, 긴급단계 대피소 위치 확인 버튼 높이
  buttonWidth: 235, //위 버튼들 너비
  policyBoxHeight: 338, //약관 및 정책 자세히 보기 박스 높이
  policyBoxWidth: 203, //약관 및 정책 자세히 보기 박스 너비
} as const;

export const radius = {
  borderRadiusSm: 6, //기본 모서리
  borderRadiusMd: 18, //약관 및 정책 자세히 보기 박스 모서리/ 길안내 흰색 박스, 대피 확인 박스
  borderRadiusLg: 30, //홈 하단 메뉴 버튼 모서리
  borderRadiusXl: 35, //대피소 안내, 대피소 변경하기 버튼 모서리
};
