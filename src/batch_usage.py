#!/usr/bin/env python3
"""
バッチ結果のusageMetadata構造をチェックするスクリプト
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# クエリファイルのキャッシュ
query_cache = {}

# Gemini API 料金設定（100万トークンあたりの米ドル）
PRICING = {
    'input_per_million': 0.10,    # テキスト、画像、動画
    'output_per_million': 0.40    # 思考トークンを含む
}


def calculate_cost(usage_stats: Dict[str, Any]) -> Dict[str, float]:
    """
    使用統計から料金を計算する
    """
    prompt_tokens = usage_stats.get('prompt_tokens', 0)
    candidates_tokens = usage_stats.get('candidates_tokens', 0)
    thoughts_tokens = usage_stats.get('thoughts_tokens', 0)
    
    # 入力コスト（プロンプトトークン）
    input_cost = (prompt_tokens / 1_000_000) * PRICING['input_per_million']
    
    # 出力コスト（候補トークン + 思考トークン）
    output_cost = ((candidates_tokens + thoughts_tokens) / 1_000_000) * PRICING['output_per_million']
    
    # 総コスト
    total_cost = input_cost + output_cost
    
    return {
        'input_cost': input_cost,
        'output_cost': output_cost,
        'total_cost': total_cost
    }


def check_usage_metadata_structure(usage_metadata: Dict[str, Any], response_data: Dict[str, Any]) -> List[str]:
    """
    usageMetadataの構造をチェックし、問題があればエラーメッセージを返す
    """
    errors = []
    
    # promptFeedbackでブロックされた場合の処理
    is_blocked = 'promptFeedback' in response_data and 'blockReason' in response_data['promptFeedback']
    
    # 必須フィールドの存在チェック
    required_fields = ['totalTokenCount', 'promptTokenCount']
    if not is_blocked:
        required_fields.append('candidatesTokenCount')
    
    for field in required_fields:
        if field not in usage_metadata:
            errors.append(f"必須フィールド '{field}' が存在しません")
        elif not isinstance(usage_metadata[field], int):
            errors.append(f"フィールド '{field}' は整数である必要があります")
    
    # promptTokensDetailsの存在チェック
    if 'promptTokensDetails' not in usage_metadata:
        errors.append("必須フィールド 'promptTokensDetails' が存在しません")
    else:
        prompt_details = usage_metadata['promptTokensDetails']
        if not isinstance(prompt_details, list):
            errors.append("'promptTokensDetails' は配列である必要があります")
        else:
            for i, detail in enumerate(prompt_details):
                if not isinstance(detail, dict):
                    errors.append(f"promptTokensDetails[{i}] は辞書である必要があります")
                    continue
                
                if 'tokenCount' not in detail:
                    errors.append(f"promptTokensDetails[{i}] に 'tokenCount' がありません")
                elif not isinstance(detail['tokenCount'], int):
                    errors.append(f"promptTokensDetails[{i}].tokenCount は整数である必要があります")
                
                if 'modality' not in detail:
                    errors.append(f"promptTokensDetails[{i}] に 'modality' がありません")
                elif not isinstance(detail['modality'], str):
                    errors.append(f"promptTokensDetails[{i}].modality は文字列である必要があります")
    
    # candidatesの構造チェック（ブロックされていない場合）
    if not is_blocked and len(errors) == 0:
        if 'candidates' not in response_data:
            errors.append("必須フィールド 'candidates' が存在しません")
        else:
            candidates = response_data['candidates']
            if not isinstance(candidates, list):
                errors.append("'candidates' は配列である必要があります")
            elif len(candidates) != 1:
                errors.append(f"'candidates' の要素数は1である必要があります（実際: {len(candidates)}）")
            else:
                candidate = candidates[0]
                if not isinstance(candidate, dict):
                    errors.append("candidates[0] は辞書である必要があります")
                else:
                    # contentの存在チェック
                    if 'content' not in candidate:
                        errors.append("candidates[0] に 'content' がありません")
                    else:
                        content = candidate['content']
                        if not isinstance(content, dict):
                            errors.append("candidates[0].content は辞書である必要があります")
                        else:
                            # partsの存在チェック
                            if 'parts' not in content:
                                errors.append("candidates[0].content に 'parts' がありません")
                            else:
                                parts = content['parts']
                                if not isinstance(parts, list):
                                    errors.append("candidates[0].content.parts は配列である必要があります")
                                elif len(parts) != 1:
                                    errors.append(f"candidates[0].content.parts の要素数は1である必要があります（実際: {len(parts)}）")
                                else:
                                    part = parts[0]
                                    if not isinstance(part, dict):
                                        errors.append("candidates[0].content.parts[0] は辞書である必要があります")
                                    else:
                                        # textフィールドの存在チェック
                                        if 'text' not in part:
                                            errors.append("candidates[0].content.parts[0] に 'text' がありません")
                                        elif not isinstance(part['text'], str):
                                            errors.append("candidates[0].content.parts[0].text は文字列である必要があります")
                                        
                                        # textフィールド以外の余分なフィールドチェック
                                        if set(part.keys()) != {'text'}:
                                            extra_fields = set(part.keys()) - {'text'}
                                            errors.append(f"candidates[0].content.parts[0] に余分なフィールド: {sorted(extra_fields)}")
    
    # トークン数の整合性チェック
    if len(errors) == 0:  # 基本構造に問題がない場合のみ
        total = usage_metadata.get('totalTokenCount', 0)
        prompt = usage_metadata.get('promptTokenCount', 0)
        candidates = usage_metadata.get('candidatesTokenCount', 0)
        thoughts = usage_metadata.get('thoughtsTokenCount', 0)  # 思考トークン（存在しない場合は0）
        
        if is_blocked:
            # ブロックされた場合はcandidatesTokenCountは0として扱う
            expected_total = prompt + thoughts
            if total != expected_total:
                thoughts_info = f" + thoughts({thoughts})" if thoughts > 0 else ""
                errors.append(f"トークン数の不整合（ブロック時）: total({total}) != prompt({prompt}){thoughts_info}")
        else:
            expected_total = prompt + candidates + thoughts
            if total != expected_total:
                thoughts_info = f" + thoughts({thoughts})" if thoughts > 0 else ""
                errors.append(f"トークン数の不整合: total({total}) != prompt({prompt}) + candidates({candidates}){thoughts_info}")
    
    return errors


def load_jsonl_as_dict(file_path: str) -> Dict[str, Any]:
    """
    JSONLファイルを読み込み、key→dictのマッピングを作成する
    """
    result = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    key = data.get('key')
                    if key:
                        result[key] = data
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return result


def get_response_file_path(query_file_path: str) -> str:
    """
    クエリファイルパスからレスポンスファイルパスを取得する
    """
    query_path = Path(query_file_path)
    return str(query_path.parent / "results" / query_path.name)


def get_query_content(query_dict: Dict[str, Any], key: str) -> Optional[str]:
    """
    クエリ辞書から指定されたキーのクエリ内容を取得する
    """
    try:
        if key in query_dict:
            return json.dumps(query_dict[key], ensure_ascii=False)
        return f"key {key} が見つかりません"
    except Exception as e:
        return f"クエリ取得エラー: {str(e)}"


def analyze_query_response_pair(query_file_path: str, show_content: bool = False) -> Dict[str, Any]:
    """
    クエリファイルと対応するレスポンスファイルを解析してusageMetadataの構造をチェックする
    """
    results = {
        'total_lines': 0,
        'valid_lines': 0,
        'invalid_lines': 0,
        'thoughts_lines': 0,
        'blocked_lines': 0,
        'blocked_details': [],
        'errors': [],
        'structure_violations': [],
        'error_lines': [],
        'key_mismatches': [],
        'usage_stats': {
            'total_tokens': 0,
            'prompt_tokens': 0,
            'candidates_tokens': 0,
            'thoughts_tokens': 0,
            'modality_stats': {}
        }
    }
    
    # クエリファイルとレスポンスファイルのパスを取得
    response_file_path = get_response_file_path(query_file_path)
    
    # クエリファイルを読み込む
    query_dict = load_jsonl_as_dict(query_file_path)
    if not query_dict:
        results['errors'].append(f"クエリファイルが読み込めません: {query_file_path}")
        return results
    
    # レスポンスファイルを読み込む
    response_dict = load_jsonl_as_dict(response_file_path)
    if not response_dict:
        results['errors'].append(f"レスポンスファイルが読み込めません: {response_file_path}")
        return results
    
    # キーの過不足チェック
    query_keys = set(query_dict.keys())
    response_keys = set(response_dict.keys())
    missing_in_response = query_keys - response_keys
    extra_in_response = response_keys - query_keys
    
    if missing_in_response:
        results['key_mismatches'].append(f"レスポンスに存在しないキー: {sorted(missing_in_response)}")
    if extra_in_response:
        results['key_mismatches'].append(f"クエリに存在しないキー: {sorted(extra_in_response)}")
    
    # レスポンスファイルの行番号付きマッピング作成
    line_mapping = {}
    try:
        with open(response_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                results['total_lines'] += 1
                
                try:
                    # JSON解析
                    data = json.loads(line.strip())
                    key = data.get('key')
                    if key:
                        line_mapping[key] = (line_num, line.strip())
                    
                except json.JSONDecodeError as e:
                    results['invalid_lines'] += 1
                    results['errors'].append(f"行{line_num}: JSON解析エラー: {str(e)}")
                    if show_content:
                        results['error_lines'].append((line_num, line.strip()))
                except Exception as e:
                    results['invalid_lines'] += 1
                    results['errors'].append(f"行{line_num}: 予期しないエラー: {str(e)}")
                    if show_content:
                        results['error_lines'].append((line_num, line.strip()))
    
    except FileNotFoundError:
        results['errors'].append(f"レスポンスファイルが見つかりません: {response_file_path}")
    except Exception as e:
        results['errors'].append(f"レスポンスファイル読み込みエラー: {str(e)}")
    
    # dictベースでの分析
    for key, data in response_dict.items():
        line_num, line_content = line_mapping.get(key, (0, ""))
        
        # usageMetadataの存在チェック
        if 'response' not in data:
            results['structure_violations'].append(f"行{line_num}: 'response' フィールドが存在しません")
            results['invalid_lines'] += 1
            if show_content:
                results['error_lines'].append((line_num, line_content))
            continue
        
        if 'usageMetadata' not in data['response']:
            results['structure_violations'].append(f"行{line_num}: 'usageMetadata' フィールドが存在しません")
            results['invalid_lines'] += 1
            if show_content:
                results['error_lines'].append((line_num, line_content))
            continue
        
        # usageMetadataの構造チェック
        usage_metadata = data['response']['usageMetadata']
        response_data = data['response']
        structure_errors = check_usage_metadata_structure(usage_metadata, response_data)
        
        # thoughtsTokenCountがある行をカウント
        if 'thoughtsTokenCount' in usage_metadata and usage_metadata['thoughtsTokenCount'] > 0:
            results['thoughts_lines'] += 1
        
        # ブロックされた行をカウント
        if 'promptFeedback' in response_data and 'blockReason' in response_data['promptFeedback']:
            results['blocked_lines'] += 1
            block_reason = response_data['promptFeedback']['blockReason']
            query = get_query_content(query_dict, key)
            results['blocked_details'].append({
                'line_number': line_num,
                'block_reason': block_reason,
                'query': query,
                'response': line_content,
                'file_path': response_file_path
            })
        
        if structure_errors:
            results['invalid_lines'] += 1
            for error in structure_errors:
                results['structure_violations'].append(f"行{line_num}: {error}")
            if show_content:
                results['error_lines'].append((line_num, line_content))
        else:
            results['valid_lines'] += 1
            
            # 有効な行のusageMetadataを集計
            results['usage_stats']['total_tokens'] += usage_metadata.get('totalTokenCount', 0)
            results['usage_stats']['prompt_tokens'] += usage_metadata.get('promptTokenCount', 0)
            results['usage_stats']['candidates_tokens'] += usage_metadata.get('candidatesTokenCount', 0)
            results['usage_stats']['thoughts_tokens'] += usage_metadata.get('thoughtsTokenCount', 0)
            
            # promptTokensDetailsの集計
            if 'promptTokensDetails' in usage_metadata:
                for detail in usage_metadata['promptTokensDetails']:
                    if isinstance(detail, dict) and 'modality' in detail and 'tokenCount' in detail:
                        modality = detail['modality']
                        token_count = detail['tokenCount']
                        if modality not in results['usage_stats']['modality_stats']:
                            results['usage_stats']['modality_stats'][modality] = 0
                        results['usage_stats']['modality_stats'][modality] += token_count
    
    return results


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="バッチ結果のusageMetadata構造をチェックするスクリプト"
    )
    parser.add_argument(
        "query_files",
        nargs="+",
        help="分析対象のクエリJSONLファイルパス（複数可）"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="ブロックされた行の詳細を表示"
    )
    
    args = parser.parse_args()
    
    # 複数ファイルの処理
    all_results = {
        'total_lines': 0,
        'valid_lines': 0,
        'invalid_lines': 0,
        'thoughts_lines': 0,
        'blocked_lines': 0,
        'blocked_details': [],
        'errors': [],
        'structure_violations': [],
        'error_lines': [],
        'usage_stats': {
            'total_tokens': 0,
            'prompt_tokens': 0,
            'candidates_tokens': 0,
            'thoughts_tokens': 0,
            'modality_stats': {}
        }
    }
    
    for query_file in args.query_files:
        results = analyze_query_response_pair(query_file, False)
        
        # 結果をマージ
        all_results['total_lines'] += results['total_lines']
        all_results['valid_lines'] += results['valid_lines']
        all_results['invalid_lines'] += results['invalid_lines']
        all_results['thoughts_lines'] += results['thoughts_lines']
        all_results['blocked_lines'] += results['blocked_lines']
        all_results['blocked_details'].extend(results['blocked_details'])
        all_results['errors'].extend(results['errors'])
        all_results['structure_violations'].extend(results['structure_violations'])
        all_results['error_lines'].extend(results['error_lines'])
        all_results['key_mismatches'] = all_results.get('key_mismatches', [])
        all_results['key_mismatches'].extend(results['key_mismatches'])
        
        # 使用統計をマージ
        all_results['usage_stats']['total_tokens'] += results['usage_stats']['total_tokens']
        all_results['usage_stats']['prompt_tokens'] += results['usage_stats']['prompt_tokens']
        all_results['usage_stats']['candidates_tokens'] += results['usage_stats']['candidates_tokens']
        all_results['usage_stats']['thoughts_tokens'] += results['usage_stats']['thoughts_tokens']
        
        # モダリティ統計をマージ
        for modality, count in results['usage_stats']['modality_stats'].items():
            if modality not in all_results['usage_stats']['modality_stats']:
                all_results['usage_stats']['modality_stats'][modality] = 0
            all_results['usage_stats']['modality_stats'][modality] += count
        
        if len(args.query_files) > 1:
            file_name = Path(query_file).name
            key_mismatch_info = f", キー不一致 {len(results['key_mismatches'])}" if results['key_mismatches'] else ""
            print(f"{file_name}: {results['total_lines']} 行, 有効 {results['valid_lines']}, 無効 {results['invalid_lines']}, 思考 {results['thoughts_lines']}, ブロック {results['blocked_lines']}{key_mismatch_info}")
    
    results = all_results
    
    # 結果の表示
    print()
    print(f"ファイル数: {len(args.query_files)}")
    print(f"総行数: {results['total_lines']}")
    print(f"有効な行数: {results['valid_lines']}")
    print(f"無効な行数: {results['invalid_lines']}")
    print(f"思考トークンありの行数: {results['thoughts_lines']}")
    print(f"ブロックされた行数: {results['blocked_lines']}")
    print()
    
    # キー不一致の表示
    if results.get('key_mismatches'):
        print("キー不一致:")
        for mismatch in results['key_mismatches']:
            print(f"  - {mismatch}")
        print()
    
    # エラー詳細を表示
    if results['errors']:
        print("エラー:")
        for error in results['errors']:
            print(f"  - {error}")
        print()
    
    if results['structure_violations']:
        print("構造違反:")
        for violation in results['structure_violations']:
            print(f"  - {violation}")
        print()
    
    # ブロック詳細を表示（--verboseオプション時のみ）
    if args.verbose and results['blocked_details']:
        print("ブロックされた行の詳細:")
        for detail in results['blocked_details']:
            file_name = Path(detail['file_path']).name
            print(f"\n{file_name}:行{detail['line_number']} - {detail['block_reason']}")
            if detail['query']:
                print()
                print(detail['query'])
            if detail['response']:
                print()
                print(detail['response'])
        print()
    
    # 使用統計の表示
    if results['usage_stats']['total_tokens'] > 0:
        # 料金計算
        cost_info = calculate_cost(results['usage_stats'])
        results['usage_stats']['cost_usd'] = cost_info
        
        print("使用統計:")
        print(json.dumps(results['usage_stats'], ensure_ascii=False, indent=2))
        print()
    
    # 成功率の計算
    if results['total_lines'] > 0:
        success_rate = (results['valid_lines'] / results['total_lines']) * 100
        print(f"構造適合率: {success_rate:.2f}%")
    
    # 終了コード
    has_errors = results['invalid_lines'] > 0 or results.get('key_mismatches', [])
    sys.exit(0 if not has_errors else 1)


if __name__ == "__main__":
    main()
