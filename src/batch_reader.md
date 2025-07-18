# バッチリーダーモジュール

## なぜこの実装が存在するか

### バッチ処理結果データの分離管理
**Problem**: SearchEngineクラスにバッチ処理結果（batch/results.jsonl）の読み込み機能が直接実装されており、責任分離の原則に反していた。また、タグデータの読み込みとタグインデックスの構築が検索エンジンの主要機能と混在し、保守性が低下していた。

**Solution**: BatchReaderクラスを作成し、バッチ処理結果の読み込みとタグインデックス構築を専門的に担当する設計とした。SearchEngineからバッチ処理に関する詳細な実装を分離し、単一責任の原則に従った設計を実現。

### 遅延初期化による性能最適化
**Problem**: バッチデータの読み込みは重い処理だが、SearchEngineのコンストラクタで即座に実行されると、バッチデータが不要な場合でも処理時間が発生する問題があった。

**Solution**: 遅延初期化パターンを採用し、initialize()メソッドが呼ばれるまでデータ読み込みを延期する設計とした。これにより、必要に応じてのみバッチデータを読み込み、起動時間を短縮。

### メタデータ駆動による柔軟性向上
**Problem**: バッチファイルのパスがハードコーディングされており、異なるデータセットや設定に対応できない問題があった。

**Solution**: reasoning VectorStoreのメタデータに含まれるsource_pathを利用し、バッチファイルのパスを動的に取得する設計とした。これにより、データセット構成の変更に対して柔軟に対応可能。