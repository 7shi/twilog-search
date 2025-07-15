# batch_vectorize

## なぜこの実装が存在するか

### バッチ処理結果のベクトル化ニーズ
**Problem**: batch/results.jsonlのreasoningとsummaryフィールドを個別にベクトル化する必要があったが、既存のvectorize.pyはCSVデータ専用の実装だった。
**Solution**: vectorize.pyから汎用化した関数をインポートし、JSONLファイルの特定フィールドを処理できる専用スクリプトを作成。

### 複数フィールドの効率的処理
**Problem**: reasoningとsummaryは異なる性質を持つため、別々のベクトル空間で管理する必要があるが、処理フローは共通化したかった。
**Solution**: フィールド名を指定して個別処理するか、bothオプションで一括処理できる柔軟な設計を採用。reasoning/、summary/ディレクトリを自動作成して各フィールドを独立管理。

### 入力ファイル基準の出力配置
**Problem**: 任意の出力ディレクトリを指定すると、複数のJSONLファイルを処理する際にファイルの関連性が不明確になり、管理が困難になる。
**Solution**: 入力JSONLファイルと同じディレクトリに出力ディレクトリを作成する方式に変更。batch/results.jsonl → batch/reasoning/、batch/summary/という直感的な配置を実現し、データの関連性を明確化した。

### 既存コードの再利用
**Problem**: ベクトル化の核心処理は同じだが、データソースの形式が異なるため重複実装になるリスクがあった。
**Solution**: vectorize.pyを汎用化してvectorize_data関数を分離し、データ読み込み部分のみを差し替える構造にした。