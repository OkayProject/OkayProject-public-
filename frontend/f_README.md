# Frontend

이 폴더는 OkayProject의 프론트엔드 앱입니다.  
React Native와 Expo를 사용합니다.

## 실행 방법

1. 처음 프로젝트를 받은 경우, 먼저 `frontend` 폴더로 이동합니다.

````bash
cd frontend

2. 필요한 패키지를 설치합니다.

```bash
npm install

3. Expo 개발 서버를 실행합니다.

```bash
npx expo start

4. iPhone에서는 기본 카메라 앱으로 터미널에 표시되는 QR 코드를 스캔한 뒤, Expo Go로 실행합니다.


## 실행이 안 될 때
1. 휴대폰과 노트북의 Wi-Fi 가 같은지 확인합니다.
안되면 휴대폰의 핫스팟으로 연결해서 하기

2. Expo Go에서 오류가 나면 아래 명령어로 실행합니다.

```bash
npx expo start --tunnel


## 주의사항
node_modules 폴더는 GitHub에 올리지 않습니다.
패키지는 package.json을 기준으로 npm install을 실행해 설치합니다.
````
