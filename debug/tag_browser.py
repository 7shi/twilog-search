#!/usr/bin/env python3
"""
タグベース情報閲覧システム（実験的実装）

目的：
- タグの本質的特性（分類・整理）を活かした情報閲覧機能の提供
- 検索システムの補助機能として、蓄積された知識の体系的把握を支援
- 将来的なsearch_engine.py統合に向けた機能検証
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
import re
from datetime import datetime

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tag_reader import TagReader
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text


class TagBrowser:
    """タグベース情報閲覧システム"""
    
    def __init__(self, tag_data_path: str):
        """
        初期化
        
        Args:
            tag_data_path: タグデータディレクトリのパス
        """
        self.console = Console()
        self.tag_reader = TagReader(tag_data_path, load_vectors=False)  # ベクトルは不要
        
        # TagReaderからデータを取得
        self.tags_data = {}  # post_id -> [tag, ...]
        for entry in self.tag_reader.tag_data:
            post_id = int(entry['post_id'])
            self.tags_data[post_id] = entry['tags']
        
        # CSVデータとsummariesデータは暫定的に空で初期化
        self.csv_data = {}
        self.summaries_data = {}
        
        # タグ統計の事前計算
        self._calculate_tag_stats()
        self._calculate_tag_cooccurrence()
    
    def _calculate_tag_stats(self) -> None:
        """タグ統計を事前計算"""
        self.tag_counts = Counter()
        self.tag_post_map = defaultdict(list)  # tag -> [post_id, ...]
        self.post_tag_map = {}  # post_id -> [tag, ...]
        self.tag_dates = defaultdict(list)  # tag -> [timestamp, ...]
        
        # タグデータからカウントを計算
        for post_id, tags in self.tags_data.items():
            tag_list = tags if isinstance(tags, list) else []
            self.post_tag_map[post_id] = tag_list
            
            for tag in tag_list:
                self.tag_counts[tag] += 1
                self.tag_post_map[tag].append(post_id)
        
        # 日付情報を収集（CSVデータから）
        if hasattr(self, 'csv_data') and self.csv_data:
            for post_id, post_data in self.csv_data.items():
                timestamp = post_data.get('timestamp', '')
                if timestamp and post_id in self.post_tag_map:
                    for tag in self.post_tag_map[post_id]:
                        self.tag_dates[tag].append(timestamp)
    
    def _calculate_tag_cooccurrence(self) -> None:
        """タグ共起関係を計算"""
        self.tag_cooccurrence = defaultdict(Counter)
        
        for post_id, tags in self.post_tag_map.items():
            # 同一投稿内のタグ組み合わせを計算
            for i, tag1 in enumerate(tags):
                for j, tag2 in enumerate(tags):
                    if i != j:  # 自分自身との共起は除外
                        self.tag_cooccurrence[tag1][tag2] += 1
    
    def show_tag_stats(self, limit: int = 50) -> None:
        """タグ使用統計を表示"""
        table = Table(title=f"タグ使用統計（上位{limit}件）")
        table.add_column("順位", style="cyan", width=6)
        table.add_column("タグ", style="green", width=30)
        table.add_column("使用回数", style="yellow", width=10)
        table.add_column("使用率", style="magenta", width=10)
        
        total_tags = sum(self.tag_counts.values())
        
        for rank, (tag, count) in enumerate(self.tag_counts.most_common(limit), 1):
            usage_rate = f"{count/total_tags*100:.2f}%"
            table.add_row(str(rank), tag, str(count), usage_rate)
        
        self.console.print()
        self.console.print(table)
        self.console.print()
        self.console.print(f"[bold blue]総タグ数: {len(self.tag_counts)}種類, 総使用回数: {total_tags}回[/bold blue]")
    
    def search_tags(self, query: str, limit: int = 20) -> List[Tuple[str, int]]:
        """
        タグ検索
        
        Args:
            query: 検索クエリ（タグ名の部分一致）
            limit: 取得件数制限
            
        Returns:
            (tag, count)のタプルリスト
        """
        query_lower = query.lower()
        matches = []
        
        for tag, count in self.tag_counts.items():
            if query_lower in tag.lower():
                matches.append((tag, count))
        
        # 使用回数順でソート
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]
    
    def show_tag_search_results(self, query: str, limit: int = 20) -> None:
        """タグ検索結果を表示"""
        results = self.search_tags(query, limit)
        
        if not results:
            self.console.print(f"[red]'{query}'に一致するタグが見つかりませんでした[/red]")
            return
        
        table = Table(title=f"タグ検索結果: '{query}'")
        table.add_column("タグ", style="green", width=40)
        table.add_column("使用回数", style="yellow", width=10)
        table.add_column("使用率", style="magenta", width=10)
        
        total_tags = sum(self.tag_counts.values())
        
        for tag, count in results:
            usage_rate = f"{count/total_tags*100:.2f}%"
            # 検索語をハイライト
            highlighted_tag = tag.replace(query, f"[bold red]{query}[/bold red]")
            table.add_row(highlighted_tag, str(count), usage_rate)
        
        self.console.print()
        self.console.print(table)
        self.console.print()
        self.console.print(f"[bold blue]マッチしたタグ: {len(results)}件[/bold blue]")
    
    def get_tag_details(self, tag: str) -> Optional[Dict[str, Any]]:
        """
        タグの詳細情報を取得
        
        Args:
            tag: タグ名
            
        Returns:
            タグ詳細情報の辞書、見つからない場合はNone
        """
        if tag not in self.tag_counts:
            return None
        
        # 基本統計
        usage_count = self.tag_counts[tag]
        post_ids = self.tag_post_map[tag]
        
        # 関連タグ（共起タグ）
        related_tags = self.tag_cooccurrence[tag].most_common(10)
        
        # 日付情報
        timestamps = self.tag_dates.get(tag, [])
        timestamps.sort()
        
        return {
            'tag': tag,
            'usage_count': usage_count,
            'post_ids': post_ids,
            'related_tags': related_tags,
            'first_used': timestamps[0] if timestamps else '',
            'last_used': timestamps[-1] if timestamps else '',
            'timeline': timestamps
        }
    
    def show_tag_details(self, tag: str) -> None:
        """タグ詳細情報を表示"""
        details = self.get_tag_details(tag)
        
        if not details:
            self.console.print(f"[red]タグ '{tag}' が見つかりませんでした[/red]")
            return
        
        # 基本情報パネル
        info_text = f"""[bold green]タグ名:[/bold green] {tag}
[bold blue]使用回数:[/bold blue] {details['usage_count']}件
[bold yellow]関連投稿:[/bold yellow] {len(details['post_ids'])}件
[bold cyan]初回使用:[/bold cyan] {details['first_used']}
[bold magenta]最終使用:[/bold magenta] {details['last_used']}"""
        
        panel = Panel(info_text, title="タグ詳細情報", border_style="bright_blue")
        self.console.print()
        self.console.print(panel)
        
        # 関連タグ表示
        if details['related_tags']:
            self.console.print()
            table = Table(title="関連タグ（共起タグ）")
            table.add_column("関連タグ", style="green", width=30)
            table.add_column("共起回数", style="yellow", width=10)
            table.add_column("共起率", style="magenta", width=10)
            
            for related_tag, cooccur_count in details['related_tags']:
                cooccur_rate = f"{cooccur_count/details['usage_count']*100:.1f}%"
                table.add_row(related_tag, str(cooccur_count), cooccur_rate)
            
            self.console.print(table)
    
    def get_posts_by_tag(self, tag: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        指定タグの投稿一覧を取得
        
        Args:
            tag: タグ名
            limit: 取得件数制限
            
        Returns:
            投稿情報のリスト
        """
        if tag not in self.tag_post_map:
            return []
        
        post_ids = self.tag_post_map[tag]
        posts = []
        
        # CSVデータから投稿情報を取得
        if hasattr(self, 'csv_data') and self.csv_data:
            for post_id in post_ids[:limit]:
                if post_id in self.csv_data:
                    post_data = self.csv_data[post_id].copy()
                    post_data['post_id'] = post_id
                    
                    # タグ情報を追加
                    if post_id in self.summaries_data:
                        post_data.update(self.summaries_data[post_id])
                    
                    posts.append(post_data)
        else:
            # CSVデータがない場合は最小限の情報で投稿リストを作成
            for post_id in post_ids[:limit]:
                post_data = {
                    'post_id': post_id,
                    'content': f'投稿ID: {post_id}',
                    'timestamp': '',
                    'user': 'unknown',
                    'url': ''
                }
                
                # タグ情報を追加
                if post_id in self.summaries_data:
                    post_data.update(self.summaries_data[post_id])
                
                posts.append(post_data)
        
        # 日付順でソート（新しい順）
        posts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return posts
    
    def show_posts_by_tag(self, tag: str, limit: int = 10) -> None:
        """指定タグの投稿一覧を表示"""
        posts = self.get_posts_by_tag(tag, limit)
        
        if not posts:
            self.console.print(f"[red]タグ '{tag}' の投稿が見つかりませんでした[/red]")
            return
        
        self.console.print()
        self.console.print(Rule(f"タグ '{tag}' の投稿一覧（最新{len(posts)}件）", style="bright_blue"))
        
        for i, post in enumerate(posts, 1):
            content = post.get('content', '').strip()
            timestamp = post.get('timestamp', '')
            user = post.get('user', 'unknown')
            url = post.get('url', '')
            
            # 内容が長い場合は切り詰め
            if len(content) > 100:
                content = content[:97] + "..."
            
            # 投稿の他のタグを表示
            post_tags = self.post_tag_map.get(post['post_id'], [])
            other_tags = [t for t in post_tags if t != tag]
            tag_text = f" #{' #'.join(other_tags)}" if other_tags else ""
            
            # 1行形式で表示
            line = (
                f"[bold cyan]{i:2d}[/bold cyan] "
                f"[yellow][{timestamp}][/yellow] "
                f"[bold blue]{user}[/bold blue] "
                f"{content}"
                f"[bright_magenta]{tag_text}[/bright_magenta]"
            )
            
            self.console.print(line)
        
        self.console.print()
        self.console.print(f"[bold blue]表示: {len(posts)}件 / 総数: {self.tag_counts.get(tag, 0)}件[/bold blue]")
    
    def get_tag_timeline(self, tag: str, group_by: str = "month") -> Dict[str, int]:
        """
        タグの使用時系列データを取得
        
        Args:
            tag: タグ名
            group_by: グループ化単位 ("year", "month", "day")
            
        Returns:
            期間別使用回数の辞書
        """
        if tag not in self.tag_dates:
            return {}
        
        timeline = Counter()
        
        for timestamp in self.tag_dates[tag]:
            try:
                # タイムスタンプを解析
                if group_by == "year":
                    period = timestamp[:4]
                elif group_by == "month":
                    period = timestamp[:7]  # YYYY-MM
                elif group_by == "day":
                    period = timestamp[:10]  # YYYY-MM-DD
                else:
                    period = timestamp
                
                timeline[period] += 1
            except (ValueError, IndexError):
                continue
        
        return dict(timeline)
    
    def show_tag_timeline(self, tag: str, group_by: str = "month") -> None:
        """タグの使用時系列を表示"""
        timeline = self.get_tag_timeline(tag, group_by)
        
        if not timeline:
            self.console.print(f"[red]タグ '{tag}' の時系列データが見つかりませんでした[/red]")
            return
        
        # 期間順でソート
        sorted_timeline = sorted(timeline.items())
        
        table = Table(title=f"タグ '{tag}' の使用時系列（{group_by}別）")
        table.add_column("期間", style="cyan", width=15)
        table.add_column("使用回数", style="yellow", width=10)
        table.add_column("グラフ", style="green", width=30)
        
        max_count = max(timeline.values()) if timeline else 1
        
        for period, count in sorted_timeline:
            # シンプルなバーグラフ
            bar_length = int(count / max_count * 20)
            bar = "█" * bar_length
            
            table.add_row(period, str(count), bar)
        
        self.console.print()
        self.console.print(table)
        self.console.print()
        self.console.print(f"[bold blue]期間数: {len(timeline)}期間, 総使用回数: {sum(timeline.values())}回[/bold blue]")


def execute_command(browser: TagBrowser, command_str: str) -> None:
    """単一コマンドを実行"""
    console = Console()
    parts = command_str.strip().split()
    
    if not parts:
        return
    
    cmd = parts[0].lower()
    
    try:
        if cmd == "help":
            help_text = """[bold blue]タグブラウザ コマンド一覧:[/bold blue]
[green]stats [limit][/green]        - タグ使用統計を表示（デフォルト: 50件）
[green]search <query> [limit][/green] - タグ名で検索（デフォルト: 20件）
[green]details <tag>[/green]        - タグの詳細情報を表示
[green]posts <tag> [limit][/green]  - タグの投稿一覧を表示（デフォルト: 10件）
[green]timeline <tag> [period][/green] - タグの使用時系列を表示（period: year/month/day）
[green]help[/green]                 - このヘルプを表示"""
            console.print(Panel(help_text, title="コマンド一覧", border_style="bright_green"))
        
        elif cmd == "stats":
            limit = int(parts[1]) if len(parts) > 1 else 50
            browser.show_tag_stats(limit)
        
        elif cmd == "search":
            if len(parts) < 2:
                console.print("[red]使用方法: search <query> [limit][/red]")
                return
            query = parts[1]
            limit = int(parts[2]) if len(parts) > 2 else 20
            browser.show_tag_search_results(query, limit)
        
        elif cmd == "details":
            if len(parts) < 2:
                console.print("[red]使用方法: details <tag>[/red]")
                return
            tag = parts[1]
            browser.show_tag_details(tag)
        
        elif cmd == "posts":
            if len(parts) < 2:
                console.print("[red]使用方法: posts <tag> [limit][/red]")
                return
            tag = parts[1]
            limit = int(parts[2]) if len(parts) > 2 else 10
            browser.show_posts_by_tag(tag, limit)
        
        elif cmd == "timeline":
            if len(parts) < 2:
                console.print("[red]使用方法: timeline <tag> [period][/red]")
                return
            tag = parts[1]
            period = parts[2] if len(parts) > 2 else "month"
            if period not in ["year", "month", "day"]:
                console.print("[red]period は year, month, day のいずれかを指定してください[/red]")
                return
            browser.show_tag_timeline(tag, period)
        
        else:
            console.print(f"[red]不明なコマンド: {cmd}[/red]")
            console.print("[yellow]利用可能コマンド: stats, search, details, posts, timeline, help[/yellow]")
    
    except Exception as e:
        console.print(f"[red]エラー: {e}[/red]")


def run_demo(browser: TagBrowser) -> None:
    """デモンストレーションを実行"""
    console = Console()
    import time
    
    demo_title = """[bold green]🏷️  タグベース情報閲覧システム デモンストレーション  🏷️[/bold green]

[yellow]このデモでは、タグの本質的特性（情報圧縮・分類指向）を活かした
情報閲覧機能の実用性を紹介します。[/yellow]
"""
    console.print(Panel(demo_title, border_style="bright_green"))
    time.sleep(2)
    
    # 1. タグ統計デモ
    console.print("\n[bold cyan]📊 機能1: タグ使用統計[/bold cyan]")
    console.print("[dim]22万件の投稿から最も使用頻度の高いタグを分析し、知識の全体像を把握[/dim]")
    time.sleep(1)
    execute_command(browser, "stats 8")
    time.sleep(3)
    
    # 2. タグ検索デモ
    console.print("\n[bold cyan]🔍 機能2: タグ検索[/bold cyan]")
    console.print("[dim]部分一致でタグを検索し、関心のある分野を効率的に探索[/dim]")
    time.sleep(1)
    execute_command(browser, "search 機械 5")
    time.sleep(3)
    
    console.print("\n[dim]別の例: 「学習」関連のタグを検索[/dim]")
    execute_command(browser, "search 学習 6")
    time.sleep(3)
    
    # 3. タグ詳細デモ
    console.print("\n[bold cyan]📋 機能3: タグ詳細分析[/bold cyan]") 
    console.print("[dim]個別タグの詳細情報と関連タグ（共起タグ）を分析[/dim]")
    time.sleep(1)
    execute_command(browser, "details 機械学習")
    time.sleep(4)
    
    console.print("\n[dim]別の例: 「プログラミング」タグの詳細[/dim]")
    execute_command(browser, "details プログラミング")
    time.sleep(4)
    
    # 4. 投稿一覧デモ
    console.print("\n[bold cyan]📝 機能4: タグ別投稿一覧[/bold cyan]")
    console.print("[dim]特定タグが付けられた投稿を直接閲覧（情報発見支援）[/dim]")
    time.sleep(1)
    execute_command(browser, "posts 深層学習 5")
    time.sleep(3)
    
    # 5. 高度な検索例
    console.print("\n[bold cyan]🚀 機能5: 高度な分析例[/bold cyan]")
    console.print("[dim]AI分野の詳細分析: 関連技術との関係性を把握[/dim]")
    time.sleep(1)
    execute_command(browser, "details AI")
    time.sleep(4)
    
    # デモ総括
    summary_text = """[bold green]✨ デモンストレーション完了 ✨[/bold green]

[yellow]このシステムの価値:[/yellow]
• [green]知識の全体俯瞰[/green]: 22万件から主要分野を瞬時に把握
• [green]効率的な探索[/green]: 部分一致検索で関心領域を素早く発見  
• [green]関連性の発見[/green]: 共起タグで新たな関心領域を発見
• [green]体系的な整理[/green]: タグの本質的特性を活かした情報分類
• [green]再発見支援[/green]: 忘れていた知見や関心領域の再発見

[yellow]次のステップ:[/yellow]
• CSVデータ統合により投稿内容・日時情報を充実
• search_engine.pyへの統合でベクトル検索との連携
• MCPサーバー経由でのAPI提供とUI統合

[cyan]コマンド例:[/cyan]
• uv run debug/tag_browser.py --stats --stats-limit 20
• uv run debug/tag_browser.py --search "深層" --search-limit 10  
• uv run debug/tag_browser.py --details "自然言語処理"
• uv run debug/tag_browser.py --posts "量子" --posts-limit 15

[green]対話モード: uv run debug/tag_browser.py --data-path batch[/green]
"""
    
    console.print()
    console.print(Panel(summary_text, title="タグベース情報閲覧システム", border_style="bright_green"))
    console.print()
    console.print("[bold yellow]🎯 実験成功: タグの本質的特性を活かした実用的な情報閲覧システムが完成![/bold yellow]")


def main():
    """メイン関数：対話的またはコマンドライン実行"""
    import argparse
    
    parser = argparse.ArgumentParser(description="タグベース情報閲覧システム")
    parser.add_argument("--data-path", default="batch",
                        help="タグデータディレクトリのパス（デフォルト: batch）")
    parser.add_argument("--stats", action="store_true", 
                        help="タグ使用統計を表示して終了")
    parser.add_argument("--stats-limit", type=int, default=50,
                        help="統計表示件数（デフォルト: 50）")
    parser.add_argument("--search", type=str, 
                        help="タグ検索を実行して終了")
    parser.add_argument("--search-limit", type=int, default=20,
                        help="検索結果件数（デフォルト: 20）")
    parser.add_argument("--details", type=str,
                        help="指定タグの詳細情報を表示して終了")
    parser.add_argument("--posts", type=str,
                        help="指定タグの投稿一覧を表示して終了")
    parser.add_argument("--posts-limit", type=int, default=10,
                        help="投稿一覧件数（デフォルト: 10）")
    parser.add_argument("--timeline", type=str,
                        help="指定タグの時系列を表示して終了")
    parser.add_argument("--timeline-period", choices=["year", "month", "day"], default="month",
                        help="時系列の期間単位（デフォルト: month）")
    parser.add_argument("--command", type=str,
                        help="単一コマンドを実行して終了（例: 'stats 10', 'search python'）")
    parser.add_argument("--quiet", action="store_true",
                        help="初期化メッセージを表示しない")
    parser.add_argument("--demo", action="store_true",
                        help="主要機能のデモンストレーションを実行")
    
    args = parser.parse_args()
    
    console = Console()
    
    # タグデータパスの設定
    tag_data_path = Path(args.data_path)
    
    if not tag_data_path.exists():
        console.print(f"[red]タグデータディレクトリが見つかりません: {tag_data_path}[/red]")
        console.print("[yellow]--data-path オプションでパスを指定してください[/yellow]")
        sys.exit(1)
    
    # 初期化
    try:
        if not args.quiet:
            console.print("[bold green]タグブラウザを初期化中...[/bold green]")
        browser = TagBrowser(str(tag_data_path))
        if not args.quiet:
            console.print("[bold green]初期化完了[/bold green]")
    except Exception as e:
        console.print(f"[red]初期化エラー: {e}[/red]")
        sys.exit(1)
    
    # コマンドライン実行モード
    if args.stats:
        execute_command(browser, f"stats {args.stats_limit}")
        return
    
    if args.search:
        execute_command(browser, f"search {args.search} {args.search_limit}")
        return
    
    if args.details:
        execute_command(browser, f"details {args.details}")
        return
    
    if args.posts:
        execute_command(browser, f"posts {args.posts} {args.posts_limit}")
        return
    
    if args.timeline:
        execute_command(browser, f"timeline {args.timeline} {args.timeline_period}")
        return
    
    if args.command:
        execute_command(browser, args.command)
        return
    
    if args.demo:
        run_demo(browser)
        return
    
    # 対話モード
    help_text = """[bold blue]タグブラウザ コマンド一覧:[/bold blue]
[green]stats [limit][/green]        - タグ使用統計を表示（デフォルト: 50件）
[green]search <query> [limit][/green] - タグ名で検索（デフォルト: 20件）
[green]details <tag>[/green]        - タグの詳細情報を表示
[green]posts <tag> [limit][/green]  - タグの投稿一覧を表示（デフォルト: 10件）
[green]timeline <tag> [period][/green] - タグの使用時系列を表示（period: year/month/day）
[green]help[/green]                 - このヘルプを表示
[green]quit[/green]                 - 終了"""
    
    console.print()
    console.print(Panel(help_text, title="タグベース情報閲覧システム", border_style="bright_green"))
    
    # 対話ループ
    while True:
        console.print()
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold yellow]プログラムを終了します[/bold yellow]")
            break
        
        if not command:
            continue
        
        if command.lower() in ["quit", "exit"]:
            console.print("[bold yellow]プログラムを終了します[/bold yellow]")
            break
        
        execute_command(browser, command)


if __name__ == "__main__":
    main()
