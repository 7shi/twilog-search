# ベクトル化モジュール

## なぜこの実装が存在するか

### CSVベースデータアクセスへの移行
**Problem**: 従来のSQLiteベースのワークフローでは、processed_contentテーブルを事前に構築する必要があり、データベースファイルの管理とメンテナンスが複雑だった。また、データ前処理のステップが多く、シンプルな検索用途には過剰な仕組みだった。

**Solution**: data_csv.pyを使用したCSVファイルからの直接データ読み込みに変更。データベース構築プロセスを完全に省略し、HTML文字実体参照のデコード処理も自動的に適用される統合されたワークフローを実現した。

### 設定ファイルの統合管理
**Problem**: CSVファイルのパスがコマンドライン引数でのみ指定され、埋め込み生成時と検索時で異なるファイルを参照する可能性があった。また、使用したCSVファイルの情報がメタデータに残らないため、後から確認できない。

**Solution**: DEFAULT_CSV定数によるデフォルト値の統一と、meta.jsonにCSVファイルのパスを相対パスで記録する機能を追加。埋め込み生成時と検索時のデータ整合性を保証し、トレーサビリティを向上させた。

### 誤操作防止のための必須引数化
**Problem**: CSVファイルのパスにデフォルト値を設定していると、引数なしで実行した際に意図しない重い変換作業が開始される可能性がある。22万件のベクトル化処理は約2時間かかるため、誤操作による無駄な処理時間とリソース消費を避ける必要がある。

**Solution**: csv_file引数を必須とし、デフォルト値を削除。明示的にファイルパスを指定することで、ユーザーの意図を明確化し、誤操作による処理実行を防止する設計とした。

### 大規模データの安全な処理が必要
**Problem**: 22万件の投稿データを一度にベクトル化すると、メモリ不足やプロセスクラッシュで処理が失敗し、数時間の処理が無駄になる可能性がある。また、全体を再実行する必要があり、開発効率が著しく低下する。

**Solution**: 1000件ずつの分割処理とチェックポイント機能を実装。途中で処理が中断されても、完了済みチャンクをスキップして再開できる設計とした。

### ファイル管理の複雑化を回避
**Problem**: 22万件を単一ファイルに格納すると、約860MBの巨大ファイルとなり、部分的な読み込みや更新が困難。また、ファイル破損時の影響範囲が大きすぎる。

**Solution**: embeddings/ディレクトリでの分割管理を採用。1000件ずつの小さなファイルにより、必要な部分のみの読み込みとリスク分散を実現した。

### 検索システムとの統合設計
**Problem**: 投稿IDとベクトルが別々に管理されると、検索結果の突合処理が複雑になり、パフォーマンスが低下する。また、データ整合性の問題が発生しやすい。

**Solution**: safetensorsファイル内にpost_idsとvectorsを同時格納。検索時の突合処理を簡素化し、データ整合性を保証する設計とした。

### Ruri3モデルの最適化
**Problem**: 汎用的な埋め込みモデルでは日本語テキストの意味的類似性を適切に捉えられない。特にSNSの短文や関西弁、スラングなどの表現に対応できない。

**Solution**: 日本語特化のRuri3モデル（cl-nagoya/ruri-v3-310m）を採用。「検索文書: 」プレフィックスによる文書検索用の最適化も実装した。

### 処理進捗の可視化
**Problem**: 22万件の処理では実行時間が長く、進捗が見えないと処理の停止判断ができない。また、処理効率の測定も困難。

**Solution**: tqdmによる詳細な進捗表示を実装。チャンクごとの処理速度と全体の進捗率を可視化し、処理効率を監視可能にした。

### デバイス選択の柔軟性
**Problem**: GPU環境とCPU環境で同じコードを実行したいが、デバイス指定が固定されていると環境に応じた最適化ができない。

**Solution**: コマンドライン引数によるデバイス選択機能を実装。CUDA環境では高速処理、CPU環境では安定性を重視した実行が可能。

### 処理時間の実測結果
**Problem**: 22万件規模の処理時間が予測できないと、運用スケジュールの計画が困難。

**Solution**: 実測データによる処理時間の把握。GPU環境（ROCm）での225,683件処理は1時間52分37秒、平均2,010件/分の処理速度を実現。分割処理により予測可能な処理時間を確保した。

### 遅延読み込みによる起動時間最適化
**Problem**: 大量のライブラリ（torch、safetensors、sentence_transformers等）を事前に読み込むと、変換不要な場合でも起動時間が長くなり、ユーザビリティが低下する。また、既存データ確認のみで処理が完了する場合にも重いライブラリが読み込まれてしまう。

**Solution**: 必要なライブラリを処理段階に応じて遅延読み込みする設計を採用。既存データ確認時はsafetensorsのみ、変換処理時にsentence_transformersを読み込むことで、不要な初期化コストを排除し、レスポンシブな動作を実現した。

### スマートな中断・再開機能
**Problem**: 従来のチャンクベースの再開機能では、post_idが連続していることを前提としており、データの一部削除や不整合があると正しく動作しない。また、実際に変換済みのpost_idを確認せずにファイル数のみで判断していた。

**Solution**: safetensorsファイルから実際のpost_idを読み取り、未変換のpost_idのみを対象とする差分処理アルゴリズムを実装。重複チェック機能により整合性を保証し、空番探索により効率的なファイル管理を実現した。

### 所要時間表示の改善
**Problem**: 処理時間が秒数のみでは、長時間処理の実際の所要時間を直感的に把握することが困難。特に1時間を超える処理では、時間・分・秒での表示が必要。

**Solution**: datetimeモジュールを使用した時間差計算により、自動的に時間:分:秒形式で表示。同時に秒数も併記することで、ログ解析やパフォーマンス測定にも対応した二重表示を実現した。

### 汎用ベクトル化関数の分離
**Problem**: batch/results.jsonlのreasoningとsummaryフィールドをベクトル化する需要が発生したが、既存のvectorize_csv関数はCSV専用の実装で再利用できなかった。

**Solution**: vectorize_data関数を分離し、データ形式に依存しない汎用ベクトル化処理を実現。CSVとJSONLの両方で同じ核心ロジックを再利用できる設計とし、コード重複を排除した。メタデータにはsource_typeフィールドを追加してデータソースの種類を記録。

### data_csvの遅延インポート化
**Problem**: batch_vectorize.pyからvectorize.pyをインポートする際に、data_csvモジュールも自動的に読み込まれ、不要な依存関係が発生していた。

**Solution**: data_csvのインポートをload_data_from_csv関数内に移動し、実際にCSV処理が必要な時のみ読み込まれる遅延インポート方式に変更。他のモジュールからの軽量なインポートを実現した。

### モデルキャッシュ機能の実装
**Problem**: batch_vectorize.pyで複数フィールド（reasoning、summary）を連続処理する際に、毎回モデルの初期化が発生し、不要な時間とメモリ消費が生じていた。

**Solution**: グローバル辞書によるモデルキャッシュ機能をget_model関数として実装。デバイス別にモデルをキャッシュし、2回目以降の呼び出しでは既存のモデルインスタンスを再利用することで、複数フィールド処理時の効率を大幅に向上させた。
