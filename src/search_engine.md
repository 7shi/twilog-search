# 検索エンジン

## なぜこの実装が存在するか

### 検索ロジックの分離と責務統一
**Problem**: search.pyファイルに検索エンジンクラスとメイン処理が混在し、TwilogServerに検索・統計・embeddings管理が混在していた。

**Solution**: SearchEngineクラスを独立したモジュールに分離し、全検索機能を統合。TwilogServerはクエリのベクトル化のみを担当するシンプルなラッパーとして設計。

### 重複除去とフィルタリング統合
**Problem**: 同じユーザーから同じ内容の投稿が複数存在し、ユーザー・日付フィルタリングが検索処理に散在していた。

**Solution**: (user, content)のタプルをキーとした重複チェック機構を常時有効で実装し、より古い投稿を優先。各フィルタリング設定クラスを検索エンジンに統合し、一元的なフィルタリング処理を実現。

### ユーザー・日付フィルタリング機能
**Problem**: 22万件の投稿に対して特定ユーザーや期間に絞った検索を行いたい場合があるが、柔軟な条件指定ができない。

**Solution**: 辞書ベースのフィルタリング設定を実装。
- ユーザー: includes/excludes/threshold_min/threshold_max
- 日付: from/to（YYYYMMDD形式・Y-M-D形式対応）
空の辞書による無効状態の判定により、シンプルで直感的な設計を実現。

### ジェネレーター型検索とメモリ効率化
**Problem**: フィルタリングや重複除去により処理量が予測できず、一括処理では無駄な処理が発生。大量データを一度にメモリに保持すると効率が悪い。

**Solution**: 検索処理をジェネレーター型に設計し、類似度順に投稿を1件ずつ処理。フィルタリング、重複除去、投稿内容取得を順次実行し、必要な件数に達した時点で処理を終了。

### ステートレス設計による並行アクセス対応
**Problem**: SearchEngineがインスタンス変数として設定を保持していたため、複数クライアントからの同時アクセス時に設定が競合していた。

**Solution**: SearchEngineから状態保持を完全に削除し、filter_search()メソッドの引数でSearchSettingsを受け取るステートレス設計に変更。各検索リクエストで独立した設定を使用することで、スレッドセーフな動作を実現。

### ユーザー投稿数データの効率的な活用
**Problem**: UserFilterSettingsがuser_post_countsを内部保持していたため、設定クラスが大量のユーザーデータを抱え込み、設定のシリアライズ時に不要なデータ転送が発生していた。

**Solution**: user_post_countsをUserFilterSettingsから分離し、is_user_allowed()メソッドの引数として渡す設計に変更。SearchEngineが一元管理し、必要時のみデータを参照する効率的なアーキテクチャを実現。

### 遅延初期化アーキテクチャの採用
**Problem**: SearchEngineのコンストラクタでCSV読み込みとembeddings読み込みが即座に実行され、インスタンス生成時に大量のメモリと時間を消費していた。

**Solution**: 遅延初期化パターンを導入し、コンストラクタではパラメータ保存のみを行い、実際の重い処理は明示的な初期化呼び出しまで延期。`initialized`フラグで初期化状態を管理し、インスタンス生成の軽量化と初期化タイミングの制御を両立。

### メタデータ・CSV設定の内部管理
**Problem**: TwilogServerとSearchEngineの両方でメタデータ読み込み処理が重複し、TwilogServerが複雑な`_load_csv_path()`処理を担当する必要があった。

**Solution**: SearchEngineのコンストラクタを`embeddings_dir`のみを受け取る設計に変更し、メタデータ・CSV設定をSearchEngine内部で管理。`get_model_name()`メソッドでTwilogServerにモデル情報を提供する単一責任の設計を採用。

### embeddings遅延読み込みによる初期化時間短縮
**Problem**: SearchEngineの`initialize()`メソッドでembeddings読み込みも実行されるため、TwilogServerの初期化時間が長大になっていた。

**Solution**: embeddings読み込みを`vector_search()`メソッドの初回実行時に遅延読み込みする設計に変更。`if self.vectors is None: self._load_embeddings()`による条件分岐で、検索処理が実際に必要になるまでembeddings読み込みを延期。CSV・ユーザーデータの読み込みは`initialize()`で実行し、embeddings読み込みのみを遅延させる２段階初期化アーキテクチャを採用。

### 高度なテキスト検索機能の実装
**Problem**: 単純な文字列マッチングでは、複数キーワードの組み合わせや除外条件を含む検索クエリに対応できず、柔軟な検索ができない問題があった。

**Solution**: シェル風パース機能（`text_proc.py`）を導入し、ダブルクォート・エスケープ・除外条件（-記号）をサポート。`search_posts_by_text()`でパースされた条件をAND/NOT論理で処理し、高度なテキスト検索を実現。

### テキストフィルタリング機能の分離
**Problem**: テキスト検索のフィルタリングロジックが`search_posts_by_text()`に埋め込まれており、将来的な複合検索（ベクトル検索結果のテキスト絞り込み）に再利用できない構造だった。

**Solution**: `filter_posts_by_text()`メソッドを分離し、include_terms/exclude_termsを受け取って投稿IDリストを返却する設計に変更。テキストフィルタリングロジックの再利用性を確保し、V→T複合検索の実装基盤を整備。

### V|T複合検索の効率的実装
**Problem**: ベクトル検索とテキスト検索を組み合わせた複合検索で、大量のベクトル検索結果をテキストフィルタリングする際の処理効率が課題だった。

**Solution**: `vector_search`メソッドに`text_filter`引数を追加し、類似度順に1件ずつテキストフィルタリングを実行してtop_kに達したら早期終了する効率的なアルゴリズムを実装。`is_post_text_match`による単一投稿のフィルタリング関数を分離し、V→T処理順序による結果の整合性を保証した。

### 内部API設計によるchunk分割の分離
**Problem**: `vector_search`メソッドでRPC通信用のchunk分割処理（Streaming Extensions対応）を実行していたため、内部APIとして使用する際にも不要な分割処理が実行され、処理が複雑化していた。

**Solution**: SearchEngineの`vector_search`をフラットな`List[Tuple[int, float]]`を返すシンプルな内部APIに変更し、chunk分割処理をRPCレイヤー（twilog_server.py）に移動。内部では単純な配列として処理し、RPC通信時のみStreaming Extensions対応の分割処理を実行する責務分離を実現。これにより、SearchEngineは純粋な検索エンジンとして機能し、通信プロトコルの詳細から分離された。
