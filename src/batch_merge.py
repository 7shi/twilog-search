#!/usr/bin/env python3
"""
バッチ処理結果をマージしてJSONLファイルを作成するスクリプト
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple
from tqdm import tqdm


def is_blocked_response(response_data: Dict[str, Any]) -> bool:
    """
    レスポンスがブロックされているかどうかを判定する
    """
    return 'promptFeedback' in response_data and 'blockReason' in response_data['promptFeedback']


def extract_text_from_response(response_data: Dict[str, Any]) -> str:
    """
    レスポンスデータからcandidates[0].content.parts[0].textを抽出する
    """
    try:
        candidates = response_data.get('candidates', [])
        if not candidates or len(candidates) == 0:
            return None
        
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            return None
            
        content = candidate.get('content', {})
        if not isinstance(content, dict):
            return None
            
        parts = content.get('parts', [])
        if not parts or len(parts) == 0:
            return None
            
        part = parts[0]
        if not isinstance(part, dict):
            return None
            
        text = part.get('text')
        if not isinstance(text, str):
            return None
            
        return text
    except Exception:
        return None


class JsonlProcessor:
    """JSONLファイルを処理してデータを抽出するクラス"""
    
    def __init__(self, llm_runaway_threshold: int = 10000):
        """
        初期化
        
        Args:
            llm_runaway_threshold: LLM暴走判定の文字数閾値
        """
        self.llm_runaway_threshold = llm_runaway_threshold
        self.results = []
        self.total_lines = 0
        self.skip_stats = {
            'line_parse_error': 0,
            'key_missing': 0,
            'key_convert_error': 0,
            'blocked_response': 0,
            'text_extract_error': 0,
            'json_parse_error': 0,
            'not_dict_error': 0,
            'llm_runaway': 0,
            'invalid_fields': 0
        }
        self.corrected_count = 0  # JSON補正件数（別管理）
        self.error_details = []
        self.text_lengths = []
    
    def process_files(self, file_paths: List[str]) -> None:
        """
        JSONLファイル群を処理する
        
        Args:
            file_paths: 処理対象のファイルパスリスト
        """
        # ファイル数で進捗表示
        for file_path in tqdm(file_paths, desc="ファイル処理"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    line_num = 0
                    for line in f:
                        line_num += 1
                        self.total_lines += 1
                    
                        # 単一行の処理を実行
                        self._process_single_line(line.strip(), file_path, line_num)
                        
            except Exception as e:
                print(f"ファイル読み込みエラー: {file_path} - {str(e)}", file=sys.stderr)
                continue
    
    def _process_single_line(self, line: str, file_path: str, line_num: int) -> None:
        """
        単一行を処理する
        
        Args:
            line: 処理対象の行データ
            file_path: ファイルパス
            line_num: 行番号
        """
        try:
            # JSON行を解析
            data = json.loads(line)
            
            # キーを取得
            key = data.get('key')
            if not key:
                self.skip_stats['key_missing'] += 1
                self.error_details.append({
                    'file': file_path,
                    'line': line_num,
                    'type': 'key_missing',
                    'data': line
                })
                return
                
            # キーをintに変換
            try:
                post_id = int(key)
            except (ValueError, TypeError):
                self.skip_stats['key_convert_error'] += 1
                self.error_details.append({
                    'file': file_path,
                    'line': line_num,
                    'type': 'key_convert_error',
                    'data': line
                })
                return
            
            # レスポンスデータからテキストを抽出
            response_data = data.get('response', {})
            
            # ブロックされているかチェック
            if is_blocked_response(response_data):
                self.skip_stats['blocked_response'] += 1
                self.error_details.append({
                    'file': file_path,
                    'line': line_num,
                    'type': 'blocked_response',
                    'data': line
                })
                return
            
            text = extract_text_from_response(response_data)
            if not text:
                self.skip_stats['text_extract_error'] += 1
                self.error_details.append({
                    'file': file_path,
                    'line': line_num,
                    'type': 'text_extract_error',
                    'data': line
                })
                return
            
            # テキスト長を記録
            self.text_lengths.append(len(text))
            
            # LLM暴走判定
            if len(text) >= self.llm_runaway_threshold:
                self.skip_stats['llm_runaway'] += 1
                self.error_details.append({
                    'file': file_path,
                    'line': line_num,
                    'type': 'llm_runaway',
                    'data': line
                })
                return
            
            # テキストをJSONとしてパース
            json_data = self._try_json_correction(text)
            if json_data is not None:
                # フィールド検証
                if self._validate_fields(json_data):
                    self.results.append((post_id, json_data))
                else:
                    self.skip_stats['invalid_fields'] += 1
                    self.error_details.append({
                        'file': file_path,
                        'line': line_num,
                        'type': 'invalid_fields',
                        'data': line
                    })
            else:
                self.skip_stats['json_parse_error'] += 1
                self.error_details.append({
                    'file': file_path,
                    'line': line_num,
                    'type': 'json_parse_error',
                    'data': line
                })
                
        except json.JSONDecodeError:
            self.skip_stats['line_parse_error'] += 1
            self.error_details.append({
                'file': file_path,
                'line': line_num,
                'type': 'line_parse_error',
                'data': line
            })
        except Exception:
            self.skip_stats['line_parse_error'] += 1
            self.error_details.append({
                'file': file_path,
                'line': line_num,
                'type': 'line_parse_error',
                'data': line
            })
    
    def _try_json_correction(self, text: str) -> Dict[str, Any]:
        """
        JSONの解析を試行し、必要に応じて補正する
        
        Args:
            text: JSON文字列
            
        Returns:
            解析されたJSONデータ、または None（解析失敗時）
        """
        try:
            json_data = json.loads(text)
            if isinstance(json_data, dict):
                return json_data
            else:
                return None
        except json.JSONDecodeError:
            # ```json ... ``` パターンの補正を試行
            corrected_text = text.strip()
            if corrected_text.startswith('```json\n') and corrected_text.endswith('```'):
                # ```json と ``` を除去
                corrected_text = corrected_text[8:-3].strip()
                try:
                    json_data = json.loads(corrected_text)
                    if isinstance(json_data, dict):
                        self.corrected_count += 1
                        return json_data
                except json.JSONDecodeError:
                    pass
            
            return None
    
    def _validate_fields(self, json_data: Dict[str, Any]) -> bool:
        """
        JSONデータがreasoning, summary, tagsの3項目のみを含むかを検証する
        
        Args:
            json_data: 検証対象のJSONデータ
            
        Returns:
            True: 正確に3項目を含む, False: 過不足がある
        """
        expected_fields = {'reasoning', 'summary', 'tags'}
        actual_fields = set(json_data.keys())
        return actual_fields == expected_fields
    
    def get_results(self) -> Tuple[List[Tuple[int, Dict[str, Any]]], int, Dict[str, int], List[Dict[str, Any]], List[int], int]:
        """
        処理結果を取得する
        
        Returns:
            results, total_lines, skip_stats, error_details, text_lengths, corrected_count
        """
        return self.results, self.total_lines, self.skip_stats, self.error_details, self.text_lengths, self.corrected_count


def process_jsonl_files(file_paths: List[str]) -> Tuple[List[Tuple[int, Dict[str, Any]]], int, Dict[str, int], List[Dict[str, Any]], List[int], int]:
    """
    JSONLファイルを処理してデータを抽出する（互換性のための関数）
    """
    processor = JsonlProcessor()
    processor.process_files(file_paths)
    return processor.get_results()


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="バッチ処理結果をマージしてJSONLファイルを作成するスクリプト"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="出力JSONLファイルのパス"
    )
    parser.add_argument(
        "input_files",
        nargs="+",
        help="入力JSONLファイルのパス（複数可）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細な統計情報とエラー詳細を表示"
    )
    
    args = parser.parse_args()
    
    # 入力ファイルの存在チェック
    valid_files = []
    for file_path in args.input_files:
        if Path(file_path).exists():
            valid_files.append(file_path)
        else:
            print(f"警告: ファイルが見つかりません: {file_path}", file=sys.stderr)
    
    if not valid_files:
        print("エラー: 有効な入力ファイルがありません", file=sys.stderr)
        sys.exit(1)
    
    # ファイルを処理
    print(f"処理対象ファイル数: {len(valid_files)}")
    data_list, total_lines, skip_stats, error_details, text_lengths, corrected_count = process_jsonl_files(valid_files)
    
    if not data_list:
        print("エラー: 有効なデータが見つかりませんでした", file=sys.stderr)
        sys.exit(1)
    
    # キーの昇順でソート
    data_list.sort(key=lambda x: x[0])
    
    # 出力ファイルに書き込み
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("出力書き込み中...")
    with open(output_path, 'w', encoding='utf-8') as f:
        for post_id, json_data in data_list:
            # {"key": post_id, **json_data} 形式で統合
            output_data = {"key": post_id, **json_data}
            f.write(json.dumps(output_data, ensure_ascii=False, separators=(',', ':')) + '\n')
    
    # 統計情報を表示
    skipped_count = total_lines - len(data_list)
    print(f"処理完了: {len(data_list)} 件のデータを {args.output} に出力しました")
    print(f"読み込み行数: {total_lines} 行, 出力件数: {len(data_list)} 件, スキップ: {skipped_count} 件")
    if corrected_count > 0:
        print(f"JSON補正: {corrected_count} 件")
    
    # スキップの内訳を表示
    if skipped_count > 0:
        print("\nスキップの内訳:")
        skip_labels = {
            'line_parse_error': '行のJSON解析エラー',
            'key_missing': 'キーなし',
            'key_convert_error': 'キー変換エラー',
            'blocked_response': 'ブロックされたレスポンス',
            'text_extract_error': 'テキスト抽出エラー',
            'json_parse_error': 'JSON解析エラー',
            'not_dict_error': '辞書形式ではない',
            'llm_runaway': 'LLM暴走（10000文字以上）',
            'invalid_fields': 'フィールド不正（reasoning,summary,tags以外）'
        }
        for key, count in skip_stats.items():
            if count > 0:
                print(f"  {skip_labels[key]}: {count} 件")
        
        # エラー詳細を表示（--verboseオプション時のみ）
        if args.verbose and error_details:
            print("\nエラー詳細:")
            for error in error_details:
                file_name = Path(error['file']).name
                
                # keyを抽出
                key = "不明"
                try:
                    data = json.loads(error['data'])
                    key = data.get('key', '不明')
                except:
                    pass
                
                print(f"  {file_name}:{error['line']} ({skip_labels[error['type']]}) key={key} len={len(error['data'])}")
                
                # LLM暴走以外の場合のみデータを表示
                if error['type'] != 'llm_runaway':
                    print(f"    {error['data']}")
    
    # テキスト長統計を表示（--verboseオプション時のみ）
    if args.verbose and text_lengths:
        print("\nテキスト長統計:")
        print(f"  有効なテキスト数: {len(text_lengths)} 件")
        print(f"  平均長: {sum(text_lengths) / len(text_lengths):.1f} 文字")
        print(f"  最短: {min(text_lengths)} 文字")
        print(f"  最長: {max(text_lengths)} 文字")
        
        # 100文字単位のヒストグラム
        print("\n文字数分布（100文字単位）:")
        max_length = max(text_lengths)
        bins = {}
        for length in text_lengths:
            bin_key = (length // 100) * 100
            bins[bin_key] = bins.get(bin_key, 0) + 1
        
        # ヒストグラム表示
        max_count = max(bins.values()) if bins else 0
        scale = min(50, max_count)  # 最大50文字の幅
        
        for bin_start in sorted(bins.keys()):
            count = bins[bin_start]
            bin_end = bin_start + 99
            bar_length = int(count * scale / max_count) if max_count > 0 else 0
            bar = '█' * bar_length
            print(f"  {bin_start:6d}-{bin_end:6d}: {count:6d} {bar}")
        
        # 異常に長いテキストの警告
        long_texts = [l for l in text_lengths if l > 50000]
        if long_texts:
            print(f"\n警告: 50000文字を超える異常に長いテキストが {len(long_texts)} 件あります")
            print(f"  最長: {max(long_texts)} 文字")


if __name__ == "__main__":
    main()
