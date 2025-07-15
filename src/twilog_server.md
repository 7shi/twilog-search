# twilog_server

## なぜこの実装が存在するか

### embed_server基底クラスの継承による拡張
**Problem**: ruri_server.pyは独自のアーキテクチャで実装されており、embed_server.pyの基底クラス設計による拡張性や動的モデル指定機能を活用できていなかった。

**Solution**: embed_server.pyのBaseEmbedServerを継承してTwilogServerクラスを実装し、基底クラスの共通機能（ライブラリ読み込み、進捗報告、WebSocket通信）を活用しつつ、VectorStore統合による正確なベクトル管理と検索機能を追加拡張する設計を採用。

### メタデータファイルからのモデル自動取得
**Problem**: 外部からモデル名を指定する方式では、embeddingsファイルと実際に使用されるモデルが不整合を起こす可能性があり、検索精度に影響を与えるリスクがあった。

**Solution**: `embeddings_meta.json`の`model`フィールドからモデル名を自動取得する設計に変更。embeddings作成時に使用されたモデルと検索時のモデルが確実に一致し、データとモデルの整合性を保証。`-m/--model`パラメータを削除し、設定ファイルベースの確実な運用を実現。

### init_model抽象メソッドの拡張実装
**Problem**: 基本的なベクトル化機能だけでなく、twilogシステム特有のembeddings読み込みと検索インデックス構築も初期化時に実行する必要があった。

**Solution**: init_modelメソッドをオーバーライドし、モデル初期化に加えてVectorStore読み込み処理を統合。SearchEngineの初期化により、3つのVectorStore（content、reasoning、summary）を独立して管理し、post_idとベクトルの正確な対応関係を保証する設計を採用。

### ruri_server.pyの完全上位互換化
**Problem**: ruri_server.pyの機能を維持しつつ、embed_serverの基底クラス設計による改善を取り込むため、既存の全機能を継承ベースで再実装する必要があった。

**Solution**: ruri_server.pyの核心機能（embeddings読み込み、類似検索、分割送信）をTwilogServerクラスに移植し、embed_serverの基底クラス機能と統合。既存のWebSocketプロトコル（embed/query）、分割送信仕様、Apache風CLI体系を完全に維持しつつ、基底クラスのメリットを活用。

### 統合的なサーバー機能の実現
**Problem**: ベクトル化のみのembed_serverと検索機能付きのruri_serverが分離していることで、用途に応じてサーバーを使い分ける必要があり、運用が複雑になっていた。

**Solution**: BaseEmbedServerの基本機能（ベクトル化）にVectorStore統合による正確なベクトル管理と検索機能を統合し、単一サーバーで両方の機能を提供。embedリクエストでベクトル化、queryリクエストで検索という明確な機能分離により、統合的な利用を可能にした。

### 拡張ポイントの活用による差分実装
**Problem**: 基底クラスの機能を活用しつつ検索機能を追加する際、全てのリクエスト処理を重複実装すると、基底クラスの改善が反映されず、保守性が低下していた。

**Solution**: `handle_additional_request`メソッドをオーバーライドして`query`リクエストのみを処理し、`status`、`check_init`、`stop`、`embed`リクエストは基底クラスに委譲。これにより、共通機能の修正は自動的に反映され、サブクラスは差分のみに集中。

### デーモン起動引数の統一設計とディレクトリ継承
**Problem**: サブクラスごとに異なるデーモン起動引数が必要な場合、従来のget_daemon_args関数による実装では引数の受け渡しが複雑になり、保守性が低下していた。また、複数のディレクトリオプションを適切に継承する仕組みが不足していた。

**Solution**: start_daemon関数にdaemon_argsリストを直接渡す設計に変更し、`--embeddings-dir`、`--reasoning-dir`、`--summary-dir`の3つの引数を一括定義で記述。コマンドライン引数で`-r/--reasoning-dir`と`-s/--summary-dir`オプション（デフォルト: `batch/reasoning`、`batch/summary`）を追加し、start commandで指定された設定を確実に_daemonプロセスに引き継ぐ統一アーキテクチャを実現。

### サーバー種別識別機能の実装
**Problem**: 複数の継承サーバー（EmbedServer、TwilogServer）が同じポートで動作する際、どのサーバーが起動しているかを識別する手段がなく、デバッグや運用監視が困難だった。

**Solution**: `get_status_response`メソッドで`self.__class__.__name__`を使用してクラス名を動的に取得し、サーバー種別を明確に識別。進捗報告でもサーバー種類を表示することで、起動時からサーバーの識別が可能になり、運用の透明性を向上。

### メタデータエラーの確実な検出と報告
**Problem**: `embeddings_meta.json`に`model`フィールドが存在しない場合、初期化時にKeyErrorが発生するが、従来のエラーハンドリングでは原因が不明で問題の特定が困難だった。

**Solution**: 基底クラスの初期化エラーハンドリングシステムを活用し、メタデータ読み込み時のKeyErrorを適切にキャッチして明確なエラーメッセージでフロント側に通知。メタデータファイルの不備を即座に特定可能にし、設定ミスによる長時間の待機状態を回避。

### JSON-RPC 2.0プロトコルの完全準拠
**Problem**: 独自JSON形式による通信により、標準的なRPCクライアントとの互換性がなく、MCPサーバーとの連携で再ラッピング処理が必要になっていた。

**Solution**: JSON-RPC 2.0標準に完全準拠したリクエスト・レスポンス形式を採用。リクエストは`{"jsonrpc": "2.0", "id": 1, "method": "vector_search", "params": {...}}`、レスポンスは`{"jsonrpc": "2.0", "id": 1, "result": {...}}`形式とし、標準エラーコード（-32600, -32601, -32602, -32603）を使用。

### メソッド名の2語化による機能の明確化
**Problem**: `search`という単語メソッド名では検索機能の具体的な種類（類似検索、テキスト検索等）が不明確で、将来的な機能拡張時に命名の衝突が懸念された。

**Solution**: メソッド名を`vector_search`に変更し、類似検索機能であることを明確化。基底クラスのメソッド名統一化（`get_status`、`stop_server`、`embed_text`）とも合わせて、API全体で2語形式による一貫性を確保。

### 旧形式サポートの完全削除
**Problem**: 後方互換性のために旧形式と新形式の両方をサポートすると、コードが複雑化し、保守性が低下する。

**Solution**: 旧形式のサポートを完全に削除し、JSON-RPC 2.0のみに統一。これにより、コードの簡潔性と保守性を向上させ、標準プロトコルへの完全移行を実現。


### SearchEngine統合による機能一元化
**Problem**: twilog_server.pyはベクトル検索のみを提供し、フィルタリング機能はクライアント側（search.py）とMCPサーバー側で重複実装されていた。この二重実装により、機能追加時の修正箇所が分散し、保守性が低下していた。また、MCPサーバーではSQLiteベースの古い実装が残存し、CSVベースの新アーキテクチャとの不整合が発生していた。

**Solution**: SearchEngineクラスをtwilog_server.pyにインポートし、フィルタリング機能を統合。meta.jsonからCSVパスを自動取得する機能を追加し、SearchEngineインスタンスの初期化を自動化。MCP互換のメソッド群（search_similar, get_user_stats, get_database_stats, search_posts_by_text）を実装し、フィルタリング済みの結果を返却。これにより、検索ロジックをサーバー側に一元化し、クライアント（search.py）とMCPサーバーは単純なWebSocketラッパーとして機能する統合アーキテクチャを実現した。

### MCPプロトコル互換API の実装
**Problem**: MCPサーバーで独自実装されていたメソッド群（search_similar、get_user_stats等）がtwilog_server.pyに存在せず、MCPサーバー側で複雑な処理を重複実装する必要があった。また、メソッド名の不整合により、API設計の一貫性が損なわれていた。

**Solution**: MCPサーバーで提供されていたメソッド名と同一のAPIをtwilog_server.pyに実装。search_similar（ベクトル検索+フィルタリング）、get_user_stats（ユーザー統計）、get_database_stats（データベース統計）、search_posts_by_text（テキスト検索）を追加し、SearchEngineとの連携により実装。これにより、MCPサーバーは単純なWebSocketラッパーとなり、処理ロジックの重複を解消。統一されたAPI設計により、CLI・MCP両方で同じメソッド名と処理結果を提供する一貫性を確保した。

### SearchSettings統合による設定管理の統一化
**Problem**: SearchEngineが状態を持つ設計により、複数クライアントからの同時アクセス時に設定が競合する問題があった。また、フィルタリング設定の受け渡しが複雑で、設定項目の追加時に複数箇所の修正が必要だった。さらに、個別パラメータ（top_k）とSearchSettings内のパラメータが重複する場合の優先順位が不明確だった。

**Solution**: SearchSettingsクラスによる統合設定管理を実装。search_similarメソッドで`settings`パラメータを受け取り、SearchSettings.from_dict()でデシリアライズしてSearchEngineに渡す設計を採用。個別の`top_k`パラメータは削除し、SearchSettingsに一元化することで設定の重複を排除。重複除去設定は常時有効とし、設定項目から除外。SearchEngineをステートレスに変更し、各リクエストで独立した設定を使用することで、並行アクセス時の競合を解消した。

### 軽量設定処理による通信効率の最適化
**Problem**: 初期の実装では、SearchSettingsにuser_post_countsが含まれていたため、クライアントから大量のユーザーデータが毎回送信され、サーバー側でも受信したuser_post_countsを既存のself.search_engine.user_post_countsに上書き設定する複雑な処理が必要だった。

**Solution**: user_post_countsをSearchSettingsから完全分離し、サーバー側での処理を大幅簡素化。search_similarメソッドでuser_post_countsの自動補完処理を削除し、SearchSettings.from_dict()では純粋な設定値のみをデシリアライズする軽量な処理に変更。SearchEngineのsearch()メソッドでは、self.user_post_countsを引数として直接渡すことで、データの重複保持と不要な通信を排除。これにより、サーバー側の処理負荷とメモリ使用量を削減し、より効率的な設定管理アーキテクチャを実現した。

### SearchEngineラッパー化とディレクトリ管理による責務分離
**Problem**: TwilogServerがSearchEngineの機能を内包する設計により責務が不明確で、固定的なディレクトリ構成のみをサポートしていたため、開発環境での柔軟な運用ができなかった。また、SearchEngineの生成タイミングが不適切で、ベクトル化機能との依存関係が複雑だった。

**Solution**: TwilogServerを完全なSearchEngineラッパーに再設計し、コンストラクタで3つの必須引数（`embeddings_dir`、`reasoning_dir`、`summary_dir`）を受け取ってディレクトリを管理。`_init_model()`でベクトル化機能初期化後にSearchEngineを生成し、`embed_func`を第1引数として渡してすべての検索処理を委譲。コマンドライン引数（`-r/--reasoning-dir`、`-s/--summary-dir`）で柔軟なディレクトリ指定を可能にし、TwilogServerは純粋なRPCラッパーとして機能する責務が明確なアーキテクチャを確立した。

### top_kバリデーションによる不正なリクエスト制限
**Problem**: 極端に大きな`top_k`値（1000件、50000件など）のリクエストが送信されると、サーバーリソースの過度な消費やメモリ不足によるクラッシュが発生する可能性があった。

**Solution**: `search_similar`メソッドで`top_k`値の事前バリデーションを実装。`top_k < 1 or top_k > 100`の場合に`ValueError`を発生させ、適切な範囲外であることを明確にエラーメッセージで通知。これにより、サーバーリソースの保護とクライアントへの明確なフィードバックを実現し、システム安定性を向上させた。

### 統計・検索API のlimitパラメータバリデーション
**Problem**: `get_user_stats`と`search_posts_by_text`メソッドで極端に大きな`limit`値が指定されると、大量のデータ処理によりサーバーリソースが枯渇し、レスポンス時間の大幅な遅延やメモリ不足が発生する可能性があった。

**Solution**: 両メソッドで`limit`パラメータの事前バリデーションを実装。`limit < 1 or limit > 1000`の場合に`ValueError`を発生させ、1-1000の適切な範囲制限を強制。MCPスキーマレベル（クライアント側）とサーバーレベル（実行時）の二重バリデーションにより、不正なリクエストを確実に遮断し、安定した統計情報提供とテキスト検索機能を確保した。

### V|T複合検索のパイプライン処理統合
**Problem**: ベクトル検索とテキスト検索を個別のAPIで提供していたため、クライアント側で複合検索を実装する際の複雑性と、通信コストの増大が課題となっていた。

**Solution**: `parse_pipeline_query`による統一構文解析を`vector_search`と`search_similar`メソッドに統合。クエリ文字列を`V|T`形式で解析し、ベクトル部分とテキスト部分を分離して処理する機能を実装。`|text`（ベクトル部分が空）の場合はテキスト検索のみを実行し、`vector|text`の場合はベクトル検索結果をテキストフィルタリングする複合検索を実行。既存APIの透明な拡張により、クライアント側の変更なしに高度な検索機能を提供した。

### RPCレイヤーでのchunk分割統合
**Problem**: SearchEngineの`vector_search`メソッドでStreaming Extensions対応のchunk分割処理を実行していたため、内部API使用時に不要な分割処理が実行され、処理効率と設計の単純性が損なわれていた。

**Solution**: chunk分割処理をSearchEngineからTwilogServerの`vector_search`メソッドに移動し、RPC通信レイヤーでのみ分割処理を実行する設計に変更。SearchEngineから`List[Tuple[int, float]]`形式のフラットな配列を受け取り、twilog_server側で2万件ずつのchunk分割とStreaming Extensions形式（`{"streaming": chunks}`）への変換を実行。これにより、内部APIは単純な配列処理を維持し、RPC通信の要件（大容量データの分割送信）は通信レイヤーで解決する責務分離を実現した。


### RPC引数形式の自然な統一化とセキュリティ強化
**Problem**: 基底クラス（embed_server.py）の`params: dict = None`形式から継承したメソッドシグネチャが不明確で、IDEでの型推論や補完機能が効果的に機能していなかった。また、動的メソッド呼び出しにより意図しないメソッドがRPC経由でアクセス可能になるセキュリティリスクが存在していた。

**Solution**: 各RPCメソッドを自然な引数形式に変更し、基底クラスの`@rpc_method`デコレーターを継承してセキュリティを強化。`vector_search(query: str, top_k: int = None)`、`search_similar(query: str, settings: dict = None)`、`get_user_stats(limit: int = 50)`、`search_posts_by_text(search_term: str, limit: int = 50)`、`suggest_users(user_list: list)`として明確なメソッドシグネチャを確立。デコレーターにより明示的にマークされたメソッドのみがRPC経由で呼び出し可能となり、APIの安全性と開発効率を両立。

### レーベンシュタイン距離による類似ユーザー検索API
**Problem**: ユーザー名入力支援機能が不足しており、タイポや表記ゆれが発生した場合に適切な候補提案ができず、ユーザー体験の向上が困難だった。また、SearchEngineで実装された類似ユーザー検索機能をRPC経由で利用するためのAPIが不足していた。

**Solution**: `suggest_users`RPCメソッドを実装し、SearchEngineの`suggest_users`機能をWebSocket経由で提供。ユーザー名リストを受け取り、存在しないユーザーに対してレーベンシュタイン距離による類似ユーザー上位5人を返却。入力バリデーション（空リスト・型チェック）を実装し、不正なリクエストを適切に遮断。クライアント・MCP両方から利用可能な統一APIとして、ユーザー名入力支援機能をサーバー側で一元提供する設計を実現。

### ハイブリッド検索システムのRPC統合
**Problem**: SearchEngineでハイブリッド検索システム（6種類の検索モード）が実装されたが、RPC経由でこれらの機能を利用するためのAPIパラメータが不足していた。投稿内容・タグ付け理由・要約の3つのベクトル空間を活用した高度な検索機能がクライアント側から利用できない状況だった。

**Solution**: `vector_search`と`search_similar`メソッドに`mode`パラメータ（デフォルト: "content"）と`weights`パラメータ（デフォルト: None）を追加。`search_posts_by_text`メソッドに`source`パラメータ（デフォルト: "content"）を追加し、3つのソース（content、reasoning、summary）からのテキスト検索を可能にした。これにより、6種類の検索モード（content、reasoning、summary、average、product、weighted）がすべてRPC経由で利用可能となり、クライアント・MCP両方から統一されたハイブリッド検索機能を提供。

