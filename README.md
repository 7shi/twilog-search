# Twilog ログ検索

Twilogのエクスポートデータからベクトル検索とタグ検索を可能にするデータ処理システム。

## 概要

CSVデータをベクトル化し、意味的類似性に基づく検索を実現するシステムです。クライアント・サーバーアーキテクチャを採用しており、WebSocketベースの検索サーバーに対してCLIクライアントとMCPクライアントの両方からアクセス可能です。

- **データ処理**: CSVファイルをRuri v3モデルでベクトル化
- **検索方式**: 意味的類似性による高精度検索 + ハイブリッド検索（6種類のモード）+ 複合検索（V|T構文）
- **アーキテクチャ**: WebSocketサーバー + 複数クライアント対応
- **クライアント**: CLI（search.py）とMCPサーバー（twilog-mcp-server）の2種類
- **実装言語**: サーバー・CLIクライアント（Python）、MCPサーバー（TypeScript）

## データ概要

- **ソースデータ**: twilog.csv（Twilogエクスポートデータ、UTF-8形式）
- **処理対象**: 投稿ID、URL、タイムスタンプ、コンテンツ、ログタイプ

## 実行手順

### 1. ベクトル化段階（必須）
```bash
uv run src/vectorize.py
```
- **入力**: twilog.csv（直接読み込み）
- **出力**: embeddings/ディレクトリ（.safetensorsファイル）
- **処理内容**: 1000件ずつの分割処理
- **処理時間**: 約1時間56分（GPU環境）
- **特徴**: 中断・再開機能対応、SQLiteデータベース不要

### 1-2. タグ付け段階（オプション）

#### リアルタイム処理（可用性検証用・保留中）
```bash
uv run src/add_tags.py twilog.csv
```
- **入力**: twilog.csv（直接読み込み）
- **出力**: tags/ディレクトリ（.jsonlファイル、1000件ずつ分割）
- **処理時間**: 約158時間（22万件、ローカルLLM）
- **特徴**: 1件ずつ処理・保存、中断・再開機能対応
- **現状**: Geminiバッチ処理完了のため保留、将来のAPI依存軽減用

#### バッチAPI処理（Gemini特化版・完了済み）
```bash
# 1. バッチリクエスト生成
uv run src/batch_generate.py twilog.csv

# 2-3. バッチジョブ投入・ポーリング・結果取得
# 注意: submit_batch.pyとpoll_batch.pyは独立プロジェクトに移行しました
# 代替ツール: https://github.com/7shi/gemini-batch

# 4. バッチ処理結果の使用統計・コスト計算
uv run src/batch_usage.py

# 5. バッチ処理結果マージ
uv run src/batch_merge.py

# 6. マージ済みデータのベクトル化
uv run src/batch_vectorize.py
```
- **batch_generate.py**: CSVからGeminiバッチAPI用JSONLリクエスト生成（1万件ずつ分割）
- **gemini-batch**: バッチジョブ管理用の独立ツール
  - 複数JSONLファイルの一括ジョブ投入・監視
  - TUIベースのリアルタイム進捗表示
  - 自動リソースクリーンアップ機能
  - インストール: `uv tool install https://github.com/7shi/gemini-batch.git`
- **batch_usage.py**: バッチ処理結果の使用統計とコスト計算（処理効率の把握）
- **batch_merge.py**: 複数バッチ結果ファイルの統合マージツール
- **batch_vectorize.py**: JSONLファイルのreasoningとsummaryフィールド別ベクトル化（batch/{reasoning,summary}/へ出力）
- **実績**: 22.5万件を23バッチで処理、総時間約9時間（158時間→9時間の17.6倍高速化）
- **品質**: 構造適合率100%、スキップ9件のみ（ブロック2件、LLM暴走7件）
- **特徴**: add_tags.pyのGemini特化版、コスト効率とスケーラビリティを重視

### 2. 検索サーバー起動段階
```bash
uv run src/twilog_server.py start
```
- **入力**: embeddings/ディレクトリ
- **機能**: WebSocketベースの検索サーバー（デーモン）
- **処理**: モデル初期化 + 埋め込みデータ読み込み
- **起動時間**: 約85秒（初回のみ）
- **特徴**: バックグラウンド実行、複数クライアント対応

### 3. ベクトル検索段階
```bash
uv run src/search.py
```
- **入力**: twilog.csv + twilog_server.py（WebSocket通信）
- **機能**: 意味的検索による投稿発見（リモート検索）
- **表示**: ランク・類似度・ユーザー・日時・URL・内容
- **特徴**: 対話的検索インターフェース（フィルタリング機能復活済み）
- **コマンド**: `/help`でヘルプ、`/user`でユーザーフィルタリング、`/date`で日付フィルタリング、`/top`で表示件数設定、`/mode`で検索モード選択
- **検索モード**: 6種類のハイブリッド検索モード（content, reasoning, summary, average, maximum, minimum）
- **検索構文**: 
  - `機械学習` - ベクトル検索のみ
  - `| "hello world" -spam` - テキスト検索のみ
  - `機械学習 | -spam` - ベクトル検索→テキスト絞り込み（複合検索）
- **起動時間**: 数秒（軽量クライアント）
- **アーキテクチャ**: twilog_server.pyのsearch_similarメソッド使用

### 4. MCP統合段階（オプション）
対話的クライアントからNode.js MCPサーバー起動
```bash
uv run src/mcp_wrap.py node -- /path/to/twilog-mcp-server/dist/index.js
```
- **Node.js MCPサーバー**: TypeScript実装のMCPラッパー（twilog-mcp-server）
- **MCPラッパー**: 対話的JSON-RPCクライアント（mcp_wrap.py）
- **機能**: ツール一覧表示、YAML出力、ヘルプ機能（`/help <tool_name>`）
- **対応ツール**: 類似検索、テキスト検索、統計情報取得、ベクトル化
- **フィルタリング**: SearchSettings対応（ユーザー・日付フィルタリング）
- **アーキテクチャ**: twilog_server.pyへの単純ラッパー（SQLite不要）
- **詳細**: [MCP サーバー詳細](mcp/README.md)


## データフロー

```
twilog.csv
    ├─ vectorize.py (CSVから直接ベクトル化)
    │   ↓
    │ embeddings/ (.safetensorsファイル + meta.json)
    │   ↓ twilog_server.py (WebSocketサーバー + SearchEngine統合 + MCP互換メソッド)
    │   ├─ search.py (軽量フロントエンド)
    │   └─ twilog-mcp-server (単純WebSocketラッパー) 
    │       └─ mcp_wrap.py (MCP対話的クライアント)
    └─ タグ付けパイプライン
        ├─ add_tags.py (リアルタイム処理) → tags/ (.jsonlファイル)
        └─ Gemini特化版
            ├─ batch_generate.py (バッチリクエスト生成) → batch/ (.jsonlファイル)
            ├─ gemini-batch (独立ツール)
            │   ├─ gembatch submit (バッチジョブ投入) → Geminiバッチ処理
            │   └─ gembatch poll (ジョブポーリング・結果取得) → batch/results/ (.jsonlファイル)
            ├─ batch_usage.py (使用統計・コスト計算) → 処理効率把握
            ├─ batch_merge.py (結果マージ) → batch/results.jsonl (.jsonl統合ファイル)
            └─ batch_vectorize.py (フィールド別ベクトル化) → batch/{reasoning,summary}/ (.safetensorsファイル)
```

## 現在の状況

### 完了済み
- ベクトル化（vectorize.py）
- 検索サーバー（twilog_server.py）
- ベクトル検索（search.py）
- V|T複合検索（パイプライン構文による統合）
- MCP統合（twilog-mcp-server + mcp_wrap.py）
- タグ付け処理パイプライン完了（Geminiバッチ処理）
  - batch_generate.py → gemini-batch → batch_merge.py → batch_vectorize.py
  - 22万件のタグ付けデータ生成完了
  - batch/results.jsonlとbatch/{reasoning,summary}/ディレクトリにデータ保存済み
- ハイブリッド検索システム（3つのベクトル空間統合）
  - 投稿内容、タグ付け理由、要約の3つのベクトル空間を統合
  - 6種類の検索モード（content, reasoning, summary, average, maximum, minimum）
  - 重み付け検索（7つのプリセット + カスタム設定）
  - search.pyの/modeコマンドによるUI統合
  - settings.pyによる設定管理とシリアライズ対応

### 次期実装予定
- タグ集計・分析システム
  - タグ使用頻度、出現パターン分析
  - タグ間の共起関係、類似度計算
  - タグの一貫性と精度の検証
- タグベース検索機能
  - 特定タグに関連する投稿の検索
  - 類似タグ発見機能
  - タグを介した関連投稿の検索
  - ベクトル検索とタグ検索の統合

### 将来実装予定（オプション）
- ローカルLLM可用性検証（Gemini vs Ollama + Qwen3）
  - 統合システム完了後の可用性検証
  - API依存リスクの軽減と選択肢の確保
  - 実用最低ラインの品質達成とローカル処理の独立性評価
  - 現状：Geminiが処理時間（9時間 vs 158時間）で圧倒的優位

## 出力ファイル

| ファイル | 件数 | 説明 |
|---------|------|------|
| embeddings/*.safetensors | 複数ファイル | ベクトルデータ |
| tags/*.jsonl | 任意 | 自動生成タグ（リアルタイム処理） |
| batch/*.jsonl | 任意 | バッチAPIリクエスト（batch_generate.py生成） |
| batch/results/*.jsonl | 任意 | バッチ処理結果（gemini-batch取得） |

## 技術仕様

- **データアクセス**: data_csv.py（CSV直接アクセス）
- **ベクトル化**: Ruri v3モデル（日本語特化）
- **検索アーキテクチャ**: WebSocketベースのサーバー・クライアント分離
- **処理方式**: 分割処理による安全性確保
- **中断・再開**: vectorize.pyで対応
- **統合アーキテクチャ**: SearchEngine中心の一元化（MCP/CLI統一）
- **設定管理**: SearchSettings（ユーザー・日付フィルタリング、表示件数）、重複除去は常時有効
- **複合検索**: V|T構文（ベクトル|テキスト）による柔軟な検索組み合わせ
- **ハイブリッド検索**: 3つのベクトル空間（content, reasoning, summary）による多次元検索
- **検索モード**: 6種類のモード（単一ソース3種 + 統合3種）、重み付け対応

## 依存関係

主要なライブラリは`pyproject.toml`で管理。各スクリプトの詳細な実装理由は対応する`.md`ファイルを参照。

### 主要コンポーネント

- **search.py**: 軽量検索フロントエンド（設定管理＋表示特化）
- **search_engine.py**: フィルタリング・重複除去の中核（ステートレス設計、twilog_server.pyで統合使用）
- **settings.py**: 統合設定管理（SearchSettings、シリアライズ対応）
- **data_csv.py**: CSVベースデータアクセス層
- **twilog_client.py**: WebSocket通信クライアント（SearchSettings対応）
- **safe_input.py**: 安全な入力処理（日本語対応）
- **twilog_server.py**: 統合WebSocketサーバー（ベクトル検索 + SearchEngine + MCP互換メソッド + 設定デシリアライズ）
- **mcp_wrap.py**: MCPプロトコル対話的クライアント
