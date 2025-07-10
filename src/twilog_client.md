# twilog_client

## なぜこの実装が存在するか

### EmbedClientからの継承による統合検索機能の提供
**Problem**: TwilogServerがSearchEngine統合により多様な検索・統計機能（search_similar、get_user_stats、get_database_stats、search_posts_by_text）を提供するようになったため、基本的な埋め込み機能のみを扱う基底クライアントでは不十分になった。

**Solution**: EmbedClientを継承したTwilogClientを実装し、基本機能を再利用しながらTwilogServer固有の全メソッドを追加。統合アーキテクチャによる豊富な機能セットをクライアント側でも完全サポート。

### WebSocketURL形式による柔軟な接続先指定
**Problem**: 基底クラスのhost/port分離形式では、WebSocketのスキーム（ws://、wss://）やパス指定が困難で、多様な接続先に対する柔軟性が不足していた。

**Solution**: `websocket_url`パラメータでURL形式の指定を採用し、urllibによる解析でhost/portに変換して基底クラスに渡す設計。URL形式による直感的な指定と既存アーキテクチャの互換性を両立。

### 分割送信対応による大量検索結果の効率的処理
**Problem**: Twilogデータベースからの検索結果は数千件規模になる可能性があり、単一レスポンスでは通信タイムアウトやメモリ使用量の問題が発生する恐れがあった。

**Solution**: サーバー側の分割送信プロトコル（`is_final`フラグによるチャンク送信）に対応した受信処理を実装。WebSocket接続を維持しながら複数レスポンスを連続受信し、最終的に統合した結果を返すアーキテクチャを採用。

### エイリアスメソッドによる既存インターフェース互換性
**Problem**: TwilogClientは基底クラスのメソッド名（`embed_text`、`stop_server`）と異なる名前（`embed`、`stop`）でのアクセスが期待される場合があり、インターフェースの一貫性確保が課題だった。

**Solution**: エイリアスメソッド（`embed`→`embed_text`、`stop`→`stop_server`）を実装し、利用者が期待する名前でのアクセスを可能にしながら、実装は基底クラスのメソッドに委譲する設計を採用。

### JSON-RPC 2.0プロトコル完全準拠
**Problem**: JSON-RPC 2.0への移行により通信プロトコルが変更され、標準準拠のクリーンな実装が求められていた。

**Solution**: `vector_search`メソッドを実装し、JSON-RPC 2.0形式（`{"jsonrpc": "2.0", "id": 1, "method": "vector_search", "params": {...}}`）に完全対応。後方互換性は削除し、標準プロトコルのみに統一してコードの簡潔性を向上。

### メソッド名の2語化による機能の明確化
**Problem**: `query`という単語メソッド名では検索機能の具体的な種類が不明確で、サーバー側の`vector_search`メソッドとの対応関係が曖昧だった。

**Solution**: 主要メソッド名を`vector_search`に変更し、サーバー側のJSON-RPCメソッド名と完全に一致させた。これにより、クライアント・サーバー間でのメソッド対応関係が明確になり、類似検索機能であることが一目瞭然に。

### TwilogCommandによる段階的CLI拡張
**Problem**: 基本的な埋め込み操作（get_status、check_init、embed_text、stop_server）に加えて、Twilog固有の検索操作（vector_search）を統一されたCLIインターフェースで提供する必要があった。

**Solution**: EmbedCommandを継承したTwilogCommandを実装し、基底クラスのargparseパーサーを拡張してvector_search機能を追加。継承により基本コマンドを自動的に利用可能にしながら、Twilog固有機能を段階的に拡張。

### TwilogServer統合メソッドの完全対応
**Problem**: TwilogServerがSearchEngine統合により提供する新機能（search_similar、get_user_stats、get_database_stats、search_posts_by_text）に対応するクライアント側実装が不足していた。

**Solution**: 各TwilogServerメソッドに対応するクライアントメソッドを実装し、パラメータ処理とレスポンス解析を適切に処理。フィルタリング付き検索、統計取得、テキスト検索の全機能をクライアントから直接利用可能に。

### CLI拡張による統合機能のコマンドライン提供
**Problem**: TwilogServerの新機能群をコマンドライン経由で利用する手段が不足しており、開発・テスト・運用での利便性が低下していた。

**Solution**: TwilogCommandクラスでargparseパーサーを拡張し、全TwilogServerメソッドに対応するコマンドを追加。各コマンドで適切な結果フォーマットと表示制限を実装し、実用的なCLIインターフェースを提供。

### 動的メソッド呼び出しによる拡張コマンドの自動統合
**Problem**: 基底クラスのEmbedCommandが提供する動的メソッド呼び出し機能を活用し、新しく追加した複数コマンド（search_similar、get_user_stats等）を既存の処理フローに自然に統合する必要があった。

**Solution**: TwilogCommandクラスに各メソッドを追加するだけで、基底クラスの`execute`メソッドが自動的に`getattr`により該当メソッドを呼び出す仕組みを活用。統合アーキテクチャの全機能を最小限の追加実装で統合。

### Streaming Extensions対応による大容量データ受信処理
**Problem**: サーバー側のStreaming Extensions実装により、検索結果が`{"data": [...], "chunk": 1, "more": true}`形式で分割送信されるため、クライアント側も対応した受信処理が必要になった。

**Solution**: `vector_search`メソッドでStreaming Extensions形式の分割受信処理を実装。`"data"`フィールドからチャンクデータを抽出し、`"more"`フラグが`false`になるまで連続受信を継続。最終的に全チャンクを統合した結果を返すことで、利用者には透過的な大容量データ処理を提供。
