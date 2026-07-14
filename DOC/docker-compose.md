# docker-compose.yml


> 여러개의 도커 컨테이너들을 단 한 번에 묶어서 실행하고 관리하기 위한 설계도 파일

---

```
networks:
  aisoc:
    driver: bridge
```

---

- `networks`는 지금부터 컨테이너들이 사용할 네트워크들을 정의한다고 선언하는 것.
- `aisoc`는 이름(식별자)로 서비스들이 여기에 가입하여 서로 통신하게 된다.
- `driver` 이 네트워크의 작동방식(종류)를 정한다. -> 네트워크 종류는 `bridge`로 정한다.
    - `bridge`
        - 도커가 제공하는 가장 표준적이고 기본이 되는 네트워크 방식이다.
        - 실제 하드웨어 장비인 **네트워크 스위치(L2 Switch)**나 **허브(Hub)**를 소프트웨어로 가상화하여 구현한 것
        - 도커의 두 종류 *기본 브릿지*와 *사용자 정의 브릿지* 중 사용자 정의 브릿지에 해당함.
        - 핵심효과
            1. 격리성
                - aisoc 네트워크에 가입된 컨테이너들끼리만 들어올 수 있는 독립된 가상 방을 만든다.
            2. 이름표로 전화걸기
                - 자동 DNS 검색(IP를 몰라도 컨테이너 이름만 가지고도 통신 가능)
            3. 보안강화
                - 폭파 반경 최소화
                - 포트 노출 최소화
        - 통신흐름
            1. 컨테이너 내부끼리의 통신
                - 속도가 빠르고 안전
            2. 외부 인터넷으로 나가기
                - NAT(Network Address Translation) 방식으로 패킷의 촐발지 IP를 컨테이너 IP에서 호스트의 실제 공인 IP로 변환하여 인터넷으로 내보낸다.
            3. 외부에서 컨테이너로 들어오기
                - 포트 포워딩(Port Publishing)을 명시해야함.
                ```
                ports:
                - "127.0.0.1:5432:5432"
                ```
                호스트 컴퓨터의 루프백 주소(127.0.0.1)의 5432포트로 들어오는 요청을 가상 브릿지 안쪽의 이 컨테이너의 5432포트로 넘겨주라는 작업.(터널 뚫기)

---

```
volumes:
  postgres_data:
  redis_data:
  kafka_data:
  clickhouse_data:
  opensearch_data:
  qdrant_data:
  neo4j_data:
  neo4j_logs:
```

---

>컨테이너가 사라져도 데이터는 절대로 지워지지 않도록 안전하게 저장할 가상 저장 공간들을 만들겠다고 선언하는 설정

---

- 도커 컨테이너는 기본적으로 휘발성
    -> 이 문제를 해결하기 위해 도커는 호스트 컴퓨터의 안전한 특정 물리 디렉토리에 공간을 확보하고, 이 공간을 컨테이너 내부의 특정 폴더와 연결(마운트Mount)해둔다.
- 공식 등록 과정이다. 변수를 선언하고 사용하는 과정과 똑같다.
- 등록하지 않고도 잘 쓰는 것들: ./로 시작하는 것은 바인드 마운트이다. 등록이 필요없다.
    - 이름만 적힌 것은 도커 엔진이 알아서 빈 가상 공간을 만들고 이름을 붙여 관리하는 네임드 볼륨이다. 공식등록(선언)이 필수이다.
- DB는 네임드 볼륨으로 만들고 등록해야한다.
    - 파일 권한 체계 충돌이 생길 수 있다.
    - 실제 폴더를 연결하면 속도가 매우 느려질 수도 있다.
- `postgres_data`(관계형 데이터)
    - 계정 정보, 보안 설정 값 등을 저장
    - 유저가 가입하고 세팅한 시스템의 가장 뼈대가 되는 구조화된 메타데이터가 보관된다.
- `redis_data`(세션 및 큐 데이터)
    - 임시 로그인 세션, 실시간 작업 대기열, 캐시 데이터 등을 저장
- `kafka_data`(실시간 이벤트 로그 메시지)
    - 네트워크, 단말, 클라우드 등에서 나오는 원본 로그 파일들을 저장한다.
- `clickhouse_data`(대용량 로그 분석 데이터)
    - 분석가들이 장기 분서을 위해 쿼리를 날릴 수 있게 압축 저장된 수십억 건의 보안 빅데이터이다.
-`opensearch_data`(검색 및 인덱스 데이터)
    -보안 로그의 원문 검색을 빠르게 하기 위해 만들어진 인덱스 구조와 파일들
- `qdrant_data`(AI인지용 벡터 데이터)
    - 보안 정보, 로그, 위협 데이터들을 고차원 숫자로 변환한 **벡터 임베딩** 데이터
- `neo4j_data` & `neo4j_logs`(관계망 그래프 및 시스템 로그)
    - `neo4j_data`
        - 자산, 네트워크 연결, 사용자 권한 간의 관계를 선과 점으로 표현한 그래프 구조 데이터. 공격 침투 경로나 연관 관계 분석을 위한 물리 파일이 담김.
    - `neo4j_logs`
        - 관계를 분석하고 탐색하는 과정에서 생성되는 Neo4j엔진 자체의 쿼리 분석 및 에러 로그 파일.

---

```
services:

  # ─── Infrastructure ─────────────────────────────────────────────────────────

  postgres:
    image: postgres:16-alpine
    container_name: aisoc-postgres
    environment:
      POSTGRES_DB: aisoc
      POSTGRES_USER: aisoc
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-aisoc_dev_secret}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./services/api/migrations:/docker-entrypoint-initdb.d:ro
    networks:
      - aisoc
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aisoc"]
      interval: 10s
      timeout: 5s
      retries: 5
```
> 관계형 데이터베이스(RDB)인 PostgreSQL을 설정하는 코드

- `postgres` 는 서비스의 고유 이름(ID)이다. 주소처럼 사용한다.
- `image: postgres:16-alpine` 어떤 이미지로 컨테이너를 만들지 지정한다.
- `container_name: aisoc-postgres` 실제 컴퓨터에서 이 컨테이너가 실행될 때 붙여질 실제 이름.
- `environment` 데이터베이스가 처음 켜질 때 세팅될 설정값을 입력한다.
- `POSTGRES_DB: aisoc` 컨테이너가 켜지면서 자동으로 생성할 **기본** 데이터베이스 이름
- `POSTGRES_USER: aisoc` 데이터베이스에 로그인할 **마스터(관리자)** 계정의 이름
- `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-aisoc_dev_secret}` .env파일에 POSTGRES_PASSWORD 설정되어 있다면 그 값 사용, (:-)비어있다면 기본값으로 aisoc_dev_secret사용

---

```
ports:
      - "127.0.0.1:5432:5432"
```
- 외부에서 데이터베이스에 접속할 수 있도록 구멍을 뚫어주는 설정.
- 127.0.0.1, 즉 내가 쓰는 이 컴퓨터 내부(localhost)에서만 직접 접속 가능

---

```
volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./services/api/migrations:/docker-entrypoint-initdb.d:ro
```
- 앞서 정의했던 postgres_data를 저장폴더(/var/lib...)에 연결함.
- migrations 데이터베이스의 테이블구조(스키마)를 정의한 SQL파일들이 있는 내 컴퓨터의 폴더
- `docker-entrypoint-initdb.d` PostgreSQL 컨테이너의 약속된 폴더. 태어나서 최초로 켜질 때 폴더의 SQL파일들을 알파벳 순서대로 실행하여 테이블을 자동으로 만들어준다.
- :ro read only 읽기 전용

---

- `networks: - aisoc` aisoc에 가입
- healthcheck 데이터베이스가 그냥 켜져 있는 척만 하는건지, 아니면 실제로 접속해서 데이터를 주고받을 준비가 완벽히 되었는지 도커가 스스로 검사하는 기능
- `test: ["CMD-SHELL", "pg_isready -U aisoc"]:` 10초마다(`interval: 10s`) 컨테이너 내부에서 pg_isready라는 명령어를 날려 데이터베이스 접속 가능 여부를 테스트
- `timeout: 5s` 테스트 명령어를 날렸을 때 5초 이상 응답이 없으면 실패로 간주한다.
- `retries: 5` 연속으로 5번 실패하면 이 데이터베이스 컨테이너의 상태를 unhealthy(비정상)로 표시

---

```
redis:
    image: redis:7-alpine
    container_name: aisoc-redis
    command: redis-server --appendonly yes --requirepass redis_dev_secret
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - aisoc
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "redis_dev_secret", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```
> 초고속 임시 메모리 저장소, 메시지 전달자인 Redis서비스 설정
Redis는 데이터를 RAM에 저장->처리 속도가 빠름. 엄청나게 빨라야 하지만 영구히 보관할 필요는 없는 임시 데이터를 다룰 때 사용.

- `command: redis-server --appendonly yes --requirepass redis_dev_secret`
- `command` 컨테이너가 켜질 때 기본 명령어가 아닌 개발자가 원하는 특정 옵션들을 붙여서 프로그램을 실행(오버라이드)하도록 지시하는 설정
- `redis-server` redis서버 프로그램을 실행하라는 기본명령
- `--appendonly yes` 이 옵션을 켜면 데이터가 변경될 때마다 디스크에 로그 파일 형식으로 기록(AOF, Append only file)한다. 초고속 속도를 유지하면서 데이터가 갑자기 날아가는 것을 방지하는 안전장치.
-> `volumes: - redis_data:/data` /data폴더에 쌓임. 이 폴더를 redis_data에 연결.
- `--requirepass redis_dev_secret` 레디스 접속시 비밀번호를 입력해야만 함.
- `ports: - "127.0.0.1:6379:6379"` Redis의 기본 통신 포트: 6379

- `test: ["CMD", "redis-cli", "-a", "redis_dev_secret", "ping"] ` redis 전용 터미널 도구 redis-cli 실행. -a redis_dev_secret 앞서 설정한 비밀번호로 로그인. ping redis 서버에게 살아있니(ping)하고 메시지를 보냄. PONG(응, 살아있어)하고 응답을 보내면 건강하다고 판단.

---

```
zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: aisoc-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    networks:
      - aisoc
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "2181"]
      interval: 10s
      timeout: 5s
      retries: 5
```
> Kafka의 관리자 역할을 하는 주키퍼. 배송센터의 컨트롤 타워나 비서 역할.

```
environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
```
- `ZOOKEEPER_TICK_TIME: 2000` 내부적으로 상태를 측정하는 기본시간단위(Tick)을 밀리초 단위로 설정한 것.(2초). 2초 동안 응답이 없으면 상태 점검을 다시하는 심장 박동 체크를 수행
- ports 설정이 없다.-> 주키퍼는 카프카와만 비밀통신을 하면 된다.

- `healthcheck: test: ["CMD", "nc", "-z", "localhost", "2181"]` nc넷캣 네트워크 연결을 테스트하는 가벼운 유틸리티 프로그램.
-z 데이터를 보내지 않고 열려있는지만 찔러보고 끝내는 옵션.

---

```
kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: aisoc-kafka
    depends_on:
      zookeeper:
        condition: service_healthy
    ports:
      - "127.0.0.1:9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
      KAFKA_LOG_RETENTION_HOURS: 168
    networks:
      - aisoc
    volumes:
      - kafka_data:/var/lib/kafka/data
    # Memory caps surface OOMKiller events as a clear container exit instead of
    # silent broker rebalances. Tune up if you raise KAFKA_HEAP_OPTS.
    mem_limit: 1536m
    mem_reservation: 1g
    healthcheck:
      test: ["CMD", "kafka-broker-api-versions", "--bootstrap-server", "localhost:9092"]
      interval: 15s
      timeout: 10s
      retries: 5
```
> Kafka는 보안로그를 실시간으로 받아 마이크로서비스로 나누어 배달해주는 분산 이벤트 스트리밍 플랫폼이다.

- `depends_on:` 주키퍼의 헬스체크 통과신호를 확인하고 나서야 카프카가 작동을 함.
- `KAFKA_BROKER_ID: 1`카프카 서버(브로커)를 구별하는 고유 ID
- `KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181` 카프카가 통제받을 비서실장(주키퍼)의 주소를 알려줌
- ` KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092` 접속하는 클라이언트에게 주소를 직접 알려줌.
PLAINTEXT://kafka:29092 내부 통신용
PLAINTEXT_HOST://localhost:9092 외부(내 PC)통신용
- `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1` 데이터 백업본(복제본)을 몇개 만들지 설정
- `KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"` 새로운 Topic 데이터가 갑자기 밀려왔을 때 관리자가 미리 방을 안만들어놨어도 카프카가 알아서 토픽을 자동생성해줌.
- `KAFKA_LOG_RETENTION_HOURS: 168` 쌓인 데이터 로그 보존 기간(그 이후에는 오래된 것부터 자동청소)
- `mem_limit: 1536m` 최대로 쓸 수 있는 메모리 제한(1.5GB)
- `mem_reservation: 1g` 실행될 때 확보할 메모리
-> 카프카는 자바(JVM)기반이라 메모리를 엄청나게 먹음. 깔끔하게 죽는 것이 에러 원인을 추적하기 편하기 때문이다.

---

```
kafka-ui:
    image: provectuslabs/kafka-ui:latest
    container_name: aisoc-kafka-ui
    depends_on:
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8090:8080"
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:29092
    networks:
      - aisoc
```
> Kafka의 내부 상태를 웹 브라우저에서 시각적으로 들여다 볼 수 있게 도와주는 시각화 도구 Kafka-UI서비스 설정

```
clickhouse:
    image: clickhouse/clickhouse-server:23.8
    container_name: aisoc-clickhouse
    ports:
      - "127.0.0.1:8123:8123"
      - "127.0.0.1:9000:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse
      - ./services/api/clickhouse:/docker-entrypoint-initdb.d:ro
    environment:
      CLICKHOUSE_DB: aisoc
      CLICKHOUSE_USER: aisoc
      CLICKHOUSE_PASSWORD: clickhouse_dev_secret
      CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1
    networks:
      - aisoc
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
    mem_limit: 1g
    mem_reservation: 768m
```
> 빅데이터급 대용량 보안 로그를 초고속으로 저장하고 분석하는 ClickHouse 서비스 설정
- `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1` 1로 이 옵션을 두면 새로운 계정을 생성하고 권한을 직접 제어할 수 있게 된다.
- `일반적인 리눅스 환경은 한 프로세스가 동시에 파일을 1,024개까지만 열 수 있게 기본 제한`
- `ulimits`: 리눅스 운영체제가 한 프로세스에게 허용하는 시스템 자원 제한을 강제로 해제하는 설정

---

```
opensearch:
    image: opensearchproject/opensearch:2.11.0
    container_name: aisoc-opensearch
    environment:
      - cluster.name=aisoc-cluster
      - node.name=aisoc-node-1
      - discovery.type=single-node
      - bootstrap.memory_lock=true
      - OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
      - DISABLE_INSTALL_DEMO_CONFIG=true
      - DISABLE_SECURITY_PLUGIN=true
    ulimits:
      memlock:
        soft: -1
        hard: -1
    volumes:
      - opensearch_data:/usr/share/opensearch/data
    ports:
      - "127.0.0.1:9200:9200"
    networks:
      - aisoc
    mem_limit: 1g
    mem_reservation: 768m
```
> 보안 로그나 검색어를 빛의 속도로 찾아주는 검색 엔진 OpenSearch

```
qdrant:
    image: qdrant/qdrant:v1.7.0
    container_name: aisoc-qdrant
    ports:
      - "127.0.0.1:6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - aisoc
```

---

> Qdrant벡터 데이터베이스 서비스

```
 neo4j:
    image: neo4j:5.15-community
    container_name: aisoc-neo4j
    ports:
      - "127.0.0.1:7474:7474"   # HTTP browser
      - "127.0.0.1:7687:7687"   # Bolt
    environment:
      NEO4J_AUTH: neo4j/neo4j_dev_secret
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_security_procedures_unrestricted: apoc.*
      NEO4J_dbms_memory_heap_initial__size: 256m
      NEO4J_dbms_memory_heap_max__size: 512m
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    networks:
      - aisoc
    mem_limit: 1g
    mem_reservation: 768m
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:7474 || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 10
```
> 인프라 자산, 네트워크 연결, 사용자 권한 간의 복잡한 관계를 그물망처럼 연결해 분석하는 그래프 데이터베이스(Graph DB)인 Neo4j(네오포제이) 서비스를 설정. 점(Node, 개체)과 선(Relationship, 관계)으로 저장하고 시각화하는 데이터베이스이다.

- `NEO4J_AUTH`  최초 로그인할 때 사용할 마스터 계정명과 비밀번호를 아이디/비밀번호 형식으로 세팅
- `NEO4J_PLUGINS: '["apoc"]'` APOC는 Neo4j세계에서의 필수 확장팩이다.
- `NEO4J_dbms_security_procedures_unrestricted: apoc.*` APOC 플러그인의 기능들이 시스템 내부 자원에 아무런 제약없이 접근할 수 있도록 보안 제한을 해제해주는 설정

---
```
# ─── Application Services ────────────────────────────────────────────────────

  api:
    build:
      context: ./services/api
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-core-api:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-api
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      REDIS_URL: redis://:redis_dev_secret@redis:6379/0
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      CLICKHOUSE_URL: http://aisoc:clickhouse_dev_secret@clickhouse:8123/aisoc
      OPENSEARCH_URL: http://opensearch:9200
      QDRANT_URL: http://qdrant:6333
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: neo4j_dev_secret
      SECRET_KEY: dev_secret_key_change_in_production
      ENVIRONMENT: development
      LOG_LEVEL: info
    # Phase 2.6 — use /readyz, not /health, so the orchestrator
    # only routes traffic once the lifespan has finished wiring
    # Postgres, Redis, Kafka, OpenSearch, Qdrant, and Neo4j.
    # /livez is what the restart policy looks at via `pgrep`-style
    # checks; we don't need a separate compose healthcheck for it
    # because the process being up implies it's alive.
    healthcheck:
      test:
        - CMD-SHELL
        - "python -c \"import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/readyz',timeout=2); sys.exit(0 if r.status==200 else 1)\" || exit 1"
      interval: 10s
      timeout: 5s
      retries: 30
      start_period: 60s
    networks:
      - aisoc
    restart: unless-stopped
```
> AiSOC 시스템의 백엔드 핵심 중의 핵심. 지휘 통제소 역할을 하는 api 서비스 설정

- `build: context: ... / dockerfile: ...` 내 컴퓨터에 있는 소스 코드(./services/api)를 바탕으로 직접 도커 이미지를 빌드(생성)
- `pull_policy: missing` 이미지를 매번 인터넷에서 새로 다운로드(Pull)하지 않고, 내 컴퓨터에 이미 빌드된 이미지가 있거나 과거 다운로드한 기록이 있다면 그것을 우선 사용
- Liveness (/livez): "이 서버 프로그램이 죽지 않고 살아있는가?" (살아있다면 굳이 재시작할 필요 없음)
- Readiness (/readyz): "살아있는 걸 넘어서, 내부적으로 Postgres, Redis, Kafka, OpenSearch, Qdrant, Neo4j 등 수많은 DB들과의 통신 연결 통로(Lifespan)를 다 뚫어서 진짜 사용자 요청을 처리할 준비가 완전히 끝났는가?"
- `restart: unless-stopped`
예상치 못한 버그나 메모리 부족으로 API 서버가 갑자기 꺼지더라도, 도커가 스스로 감지하여 백그라운드에서 자동으로 서버를 다시 켜주는(Restart) 강력한 유지보수 옵션

```
ingest-worker:
    build:
      context: ./services/ingest
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-ingest:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-ingest
    depends_on:
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8081:8080"
      - "127.0.0.1:9090:9090"
    environment:
      ENV: development
      HTTP_PORT: 8080
      METRICS_PORT: 9090
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_URL: redis://:redis_dev_secret@redis:6379/1
      LOG_LEVEL: info
      JWT_SECRET: dev_secret_key_change_in_production
      ATTCK_DATA_PATH: /app/data/enterprise-attack.json
    networks:
      - aisoc
    restart: unless-stopped
```
> ingest-worker (로그 수집 및 가공기) 서비스를 설정

```
enrichment:
    build:
      context: ./services/enrichment
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-enrichment:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-enrichment
    depends_on:
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8080:8082"
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_URL: redis://:redis_dev_secret@redis:6379/2
      VIRUSTOTAL_API_KEY: ${VIRUSTOTAL_API_KEY:-}
      ABUSEIPDB_API_KEY: ${ABUSEIPDB_API_KEY:-}
      GREYNOISE_API_KEY: ${GREYNOISE_API_KEY:-}
      SHODAN_API_KEY: ${SHODAN_API_KEY:-}
    networks:
      - aisoc
    restart: unless-stopped
```
> 보안 로그의 가치와 위협 판단 정보를 한층 더 깊고 풍부하게 만들어주는 enrichment (정보 보강 및 컨텍스트 부여) 서비스를 설정

---

```
fusion:
    build:
      context: ./services/fusion
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-fusion:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-fusion
    depends_on:
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8003:8003"
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_URL: redis://:redis_dev_secret@redis:6379/3
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
    networks:
      - aisoc
    restart: unless-stopped
```
> 수많은 개별 보안 경고들을 연관 지어 하나의 의미 있는 '보안 사고(Incident)'로 병합해 주는 fusion (이벤트 상관분석 및 병합 Engine) 서비스를 설정

```
agents:
    build:
      context: ./services/agents
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-agents:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-agents
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "127.0.0.1:8001:8084"
    environment:
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      REDIS_URL: redis://:redis_dev_secret@redis:6379/4
      CORE_API_URL: http://api:8000
      QDRANT_URL: http://qdrant:6333
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: neo4j_dev_secret
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      OPENAI_MODEL: ${OPENAI_MODEL:-gpt-4o-mini}
      ATTCK_DATA_PATH: /app/data/enterprise-attack.json
    networks:
      - aisoc
    restart: unless-stopped
```
> agents (AI 보안 분석 에이전트) 서비스를 설정

```
osquery-tls:
    build:
      context: ./services/osquery-tls
      dockerfile: Dockerfile
    # Not in publish-images.yml matrix yet — pull falls back to local build.
    image: ghcr.io/beenuar/aisoc-osquery-tls:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-osquery-tls
    depends_on:
      postgres:
        condition: service_healthy
    # Host port 8007 was previously colliding with the `ueba` service's
    # 127.0.0.1:8007 binding; remapped to 8091 here. UEBA still owns 8007.
    ports:
      - "127.0.0.1:8091:8007"
    profiles:
      - osquery
    environment:
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      AISOC_OSQUERY_TLS_ENROLL_SECRET: ${AISOC_OSQUERY_TLS_ENROLL_SECRET:-change-me-in-production}
      # The ingest service is registered as `ingest-worker` in this compose
      # file; the previous `http://ingest:8080` would not resolve via DNS.
      AISOC_INGEST_BASE_URL: http://ingest-worker:8080
    networks:
      - aisoc
    restart: unless-stopped
```
> 각 컴퓨터(서버, 사용자 PC 등)의 상태를 아주 정밀하게 감시하는 osquery-tls (단말 보안 정보 수집 서버) 서비스를 설정

```
actions:
    build:
      context: ./services/actions
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-actions:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-actions
    depends_on:
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8002:8085"
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_URL: redis://:redis_dev_secret@redis:6379/5
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      CORE_API_URL: http://api:8000
    networks:
      - aisoc
    restart: unless-stopped
```
> 위협이 발견되었을 때 실질적으로 방어 및 대응 작업을 실행하는 actions (보안 조치 실행기 / SOAR 엔진) 서비스를 설정

```
connectors:
    build:
      context: ./services/connectors
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-connectors:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-connectors
    depends_on:
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "127.0.0.1:8088:8003"
    profiles:
      - connectors
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_URL: redis://:redis_dev_secret@redis:6379/6
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      CORE_API_URL: http://api:8000
      CROWDSTRIKE_CLIENT_ID: ${CROWDSTRIKE_CLIENT_ID:-}
      CROWDSTRIKE_CLIENT_SECRET: ${CROWDSTRIKE_CLIENT_SECRET:-}
      AWS_REGION: ${AWS_REGION:-us-east-1}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-}
    networks:
      - aisoc
    restart: unless-stopped
```

 > 외부의 다양한 상용 클라우드 서비스나 기업용 보안 솔루션으로부터 보안 로그와 이벤트를 안전하게 연동해오는 connectors (외부 연동 어댑터 / 커넥터) 서비스를 설정
> 
```
threatintel:
    build:
      context: ./services/threatintel
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-threatintel:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-threatintel
    depends_on:
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8005:8005"
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_URL: redis://:redis_dev_secret@redis:6379/7
      OPENSEARCH_URL: http://opensearch:9200
      QDRANT_URL: http://qdrant:6333
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: neo4j_dev_secret
      MISP_URL: ${MISP_URL:-}
      MISP_API_KEY: ${MISP_API_KEY:-}
      OTX_API_KEY: ${OTX_API_KEY:-}
      TAXII_URL: ${TAXII_URL:-}
      TAXII_USERNAME: ${TAXII_USERNAME:-}
      TAXII_PASSWORD: ${TAXII_PASSWORD:-}
    networks:
      - aisoc
    restart: unless-stopped
```
> 전 세계에서 실시간으로 발생하는 최신 해킹 수법, 악성 IP, 악성코드 해시값 등 다양한 위협 데이터를 수집하여 우리 시스템에 동기화해 주는 threatintel (위협 인텔리전스 동기화) 서비스를 설정

```
ueba:
    build:
      context: ./services/ueba
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-ueba:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-ueba
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8007:8004"
    environment:
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      REDIS_URL: redis://:redis_dev_secret@redis:6379/8
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      CLICKHOUSE_URL: http://aisoc:clickhouse_dev_secret@clickhouse:8123/aisoc
      CORE_API_URL: http://api:8000
    networks:
      - aisoc
    restart: unless-stopped
```
> 사용자(임직원)와 각종 장비(서버, PC 등)의 평소 행동 패턴을 학습하여 이상 행동을 찾아내는 ueba (사용자 및 개체 행동 분석) 서비스를 설정

```
honeytokens:
    # Gated behind the `extras` profile: image isn't published to GHCR yet, so
    # `aisoc serve` skips it by default. Opt in with `--profile extras` and the
    # local Dockerfile build will run.
    profiles: ["extras"]
    build:
      context: ./services/honeytokens
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-honeytokens:${AISOC_VERSION:-latest}
    pull_policy: build
    container_name: aisoc-honeytokens
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8008:8005"
    environment:
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      REDIS_URL: redis://:redis_dev_secret@redis:6379/9
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      CORE_API_URL: http://api:8000
    networks:
      - aisoc
    restart: unless-stopped
```
> 해커를 유인하기 위한 가짜 미끼 자산을 배치하고 감시하는 honeytokens (디셉션 테크놀로지 / 기만 보안) 서비스를 설정

- 선택적 추가 모듈 (profiles: ["extras"])
- docker compose up을 실행하면 이 서비스는 기동하지 않고 건너뛴다.

- pull_policy: build 무조건 직접 빌드

```
purple-team:
    # Gated behind the `extras` profile: image isn't published to GHCR yet, so
    # `aisoc serve` skips it by default. Opt in with `--profile extras` and the
    # local Dockerfile build will run.
    profiles: ["extras"]
    build:
      context: ./services/purple-team
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-purple-team:${AISOC_VERSION:-latest}
    pull_policy: build
    container_name: aisoc-purple-team
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "127.0.0.1:8006:8006"
    environment:
      DATABASE_URL: postgresql+asyncpg://aisoc:${POSTGRES_PASSWORD:-aisoc_dev_secret}@postgres:5432/aisoc
      REDIS_URL: redis://:redis_dev_secret@redis:6379/10
      CORE_API_URL: http://api:8000
      ATTCK_DATA_PATH: /app/data/enterprise-attack.json
    networks:
      - aisoc
    restart: unless-stopped
```
> 가상의 공격을 우리 시스템에 직접 수행하여 방어 체계가 잘 작동하는지 모의 훈련을 진행하는 purple-team (모의 침투 및 방어 시뮬레이터) 서비스를 설정

```
realtime:
    build:
      context: ./services/realtime
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-realtime:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-realtime
    depends_on:
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
    ports:
      - "127.0.0.1:8086:4000"
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_URL: redis://:redis_dev_secret@redis:6379
      REDIS_PASSWORD: redis_dev_secret
      PORT: 4000
    networks:
      - aisoc
    restart: unless-stopped
```
> 관제 대시보드를 보고 있는 보안 분석가의 화면에 1초의 지연도 없이 실시간으로 보안 경고나 AI 에이전트의 움직임을 뿌려주는 realtime (실시간 웹소켓 통신 서버) 서비스를 설정

```
# ChatOps adapter. Holds no state — forwards `/aisoc …` slash commands and
  # approval-card button clicks to services/api and services/actions. Runs
  # under the `chatops` profile so a default `docker compose up` doesn't fail
  # when the operator has not yet provisioned a Slack app or service tokens.
  slack-bot:
    build:
      context: ./services/slack-bot
      dockerfile: Dockerfile
    image: ghcr.io/beenuar/aisoc-slack-bot:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-slack-bot
    depends_on:
      - api
      - actions
    ports:
      - "127.0.0.1:8009:8089"
    profiles:
      - chatops
    environment:
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN:-}
      SLACK_SIGNING_SECRET: ${SLACK_SIGNING_SECRET:-}
      AISOC_API_BASE_URL: http://api:8000
      AISOC_ACTIONS_BASE_URL: http://actions:8085
      AISOC_API_SERVICE_TOKEN: ${AISOC_SLACK_API_TOKEN:-}
      AISOC_ACTIONS_SERVICE_TOKEN: ${AISOC_SLACK_ACTIONS_TOKEN:-}
      AISOC_DEFAULT_TENANT_ID: ${AISOC_DEFAULT_TENANT_ID:-00000000-0000-0000-0000-000000000000}
      AISOC_WEB_BASE_URL: ${AISOC_WEB_BASE_URL:-http://localhost:3000}
      AISOC_SLACK_BOT_PORT: 8089
      AISOC_HTTP_TIMEOUT_SECONDS: 10
    networks:
      - aisoc
    restart: unless-stopped
```
> 협업 메신저인 슬랙(Slack)을 통해 보안관제팀이 메신저 창에서 편리하게 보안 시스템을 통제하고 대응하게 돕는 slack-bot (ChatOps 어댑터) 서비스를 설정

```
web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
    image: ghcr.io/beenuar/aisoc-web:${AISOC_VERSION:-latest}
    pull_policy: missing
    container_name: aisoc-web
    depends_on:
      - api
      - realtime
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
      NEXT_PUBLIC_WS_URL: ws://localhost:8086
      NODE_ENV: production
    networks:
      - aisoc
    restart: unless-stopped
```
> 웹 대시보드 화면이자 사용자 인터페이스(UI)인 web (프론트엔드 웹) 서비스를 설정

```
# ─── Observability ────────────────────────────────────────────────────────────

  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: aisoc-prometheus
    ports:
      - "127.0.0.1:9091:9090"
    volumes:
      - ./infra/docker/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      # Phase 2.4 — alert rules mounted as a directory so adding a
      # new rule file under `infra/docker/alerts/` is picked up on
      # next `docker compose restart prometheus` (or a SIGHUP).
      - ./infra/docker/alerts:/etc/prometheus/alerts:ro
    # Phase 2.4 — Prometheus needs to reach the Alertmanager service
    # before it can forward alerts. The `depends_on` keeps `docker
    # compose up monitoring` healthy on cold boot — without it,
    # Prometheus logs "level=warn ... alertmanager_url=... err=lookup"
    # for the first ~30s of every restart.
    depends_on:
      - alertmanager
    networks:
      - aisoc
    profiles:
      - monitoring
```
> AiSOC 전체 시스템이 아프지 않고 정상적으로 숨 쉬고 있는지, CPU나 메모리는 얼마나 쓰고 있는지 등의 성능 지표(Metrics)를 수시로 수집하고 감시하는 모니터링 엔진인 prometheus (프로메테우스) 서비스를 설정

- Prometheus는 현대 클라우드 및 마이크로서비스(MSA) 환경에서 사실상 표준(De-facto standard)으로 자리 잡은 시계열 데이터베이스(TSDB) 기반의 모니터링 시스템

```
# Phase 2.4 — in-cluster Alertmanager. Receives firing alerts
  # from Prometheus, groups + deduplicates them per
  # `infra/docker/alertmanager.yml`, and forwards them to the
  # configured receivers. The dev stack ships with a no-op webhook
  # receiver that points at the API's `/internal/alerts/sink`
  # endpoint (which logs the payload); production operators replace
  # the receiver block with PagerDuty / Slack / Opsgenie. The
  # `monitoring` profile keeps it out of `docker compose up`'s
  # default surface so a stock `aisoc serve` doesn't fail when the
  # operator hasn't provisioned downstream alerting.
  alertmanager:
    image: prom/alertmanager:v0.27.0
    container_name: aisoc-alertmanager
    ports:
      - "127.0.0.1:9094:9093"
    volumes:
      - ./infra/docker/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
      # External URL is what Alertmanager uses to render deep-links
      # in notification templates (e.g. "Silence in Alertmanager").
      # Port 9094 here matches the host-side mapping so the link
      # works from a browser on the operator's laptop.
      - '--web.external-url=http://localhost:9094'
    # NOTE: The Alertmanager binary does NOT substitute shell-style
    # env vars in `alertmanager.yml`. To change receivers per
    # environment, mount a different config file (production
    # deployments do this through Helm values templating).
    networks:
      - aisoc
    profiles:
      - monitoring
```
> Prometheus(프로메테우스)가 감시 도중 장애나 위험을 감지하여 쏜 비상 신호(Alert)를 받아, 담당자에게 이메일, 슬랙, 페이저듀티(PagerDuty) 등으로 똑똑하게 전달해 주는 alertmanager (비상 경고 전송 및 제어기) 서비스를 설정

- 단순 알림 도구를 안쓰고 Alertmanager거치는 이유
    - 중복제거
    - 그룹화
    - 알림 제어

```
grafana:
    image: grafana/grafana:10.2.0
    container_name: aisoc-grafana
    depends_on:
      - prometheus
    ports:
      - "127.0.0.1:3001:3000"
    # Default admin password is intentionally weak for the dev compose stack;
    # the 127.0.0.1 binding above keeps the dashboard off the LAN. Override
    # GF_SECURITY_ADMIN_PASSWORD in production deployments (helm/terraform).
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
    volumes:
      - ./infra/docker/grafana:/etc/grafana/provisioning:ro
    networks:
      - aisoc
    profiles:
      - monitoring
```
> 수집된 시스템 성능 지표(Prometheus 데이터)를 바탕으로, 서버의 상태와 리소스 사용량을 화려하고 예쁜 그래프와 차트로 그려서 눈으로 보여주는 grafana (시각화 대시보드) 서비스를 설정
