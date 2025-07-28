import logging
import requests
from typing import Optional, Dict, Any, List
import random
import time
import asyncio
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class ProxyStatus(Enum):
    """代理状态枚举"""
    ACTIVE = "active"
    FAILED = "failed"
    BLOCKED = "blocked"
    TESTING = "testing"
    COOLDOWN = "cooldown"

@dataclass
class ProxyInfo:
    """代理信息数据类"""
    host: str
    port: int
    country: str = "Unknown"
    protocol: str = "http"
    username: str = ""
    password: str = ""
    status: ProxyStatus = ProxyStatus.ACTIVE
    last_used: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    blocked_until: Optional[datetime] = None
    response_time: float = 0.0
    
    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = ProxyStatus(self.status)
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    @property
    def is_available(self) -> bool:
        """是否可用"""
        if self.status != ProxyStatus.ACTIVE:
            return False
        if self.blocked_until and datetime.now() < self.blocked_until:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        data['last_used'] = self.last_used.isoformat() if self.last_used else None
        data['last_failure'] = self.last_failure.isoformat() if self.last_failure else None
        data['blocked_until'] = self.blocked_until.isoformat() if self.blocked_until else None
        return data

class IPService:
    """增强版IP切换服务 - 支持礼品卡付款时的智能IP切换"""
    
    def __init__(self, proxy_api_url: str = "", rotation_enabled: bool = False, test_mode: bool = False):
        self.proxy_api_url = proxy_api_url
        self.rotation_enabled = rotation_enabled
        self.test_mode = test_mode  # 测试模式，跳过真实代理验证
        self.current_proxy: Optional[ProxyInfo] = None
        self.proxy_pool: List[ProxyInfo] = []
        self.last_rotation_time = 0
        self.rotation_interval = 300  # 5分钟轮换一次
        self.gift_card_rotation_enabled = True  # 礼品卡专用IP切换
        self.blocked_ips = set()  # 被封禁的IP记录
        self.gift_card_usage_history = {}  # 礼品卡使用历史 {card_number: [ip_list]}
        self.max_gift_card_per_ip = 2  # 每个IP最多使用多少张礼品卡
        
    def initialize_proxy_pool(self) -> bool:
        """初始化代理池"""
        try:
            if not self.rotation_enabled:
                logger.info("Proxy rotation disabled")
                return True
                
            # 从代理API获取代理列表
            if self.proxy_api_url:
                response = requests.get(f"{self.proxy_api_url}/proxies", timeout=10)
                proxy_data = response.json().get('proxies', [])
                
                self.proxy_pool = []
                for proxy in proxy_data:
                    proxy_info = ProxyInfo(
                        host=proxy['host'],
                        port=proxy['port'],
                        country=proxy.get('country', 'Unknown'),
                        protocol=proxy.get('protocol', 'http'),
                        username=proxy.get('username', ''),
                        password=proxy.get('password', '')
                    )
                    self.proxy_pool.append(proxy_info)
            else:
                # 模拟代理池用于测试
                mock_proxies = [
                    {'host': '127.0.0.1', 'port': 8080, 'country': 'US'},
                    {'host': '127.0.0.1', 'port': 8081, 'country': 'UK'},  
                    {'host': '127.0.0.1', 'port': 8082, 'country': 'CA'},
                    {'host': '127.0.0.1', 'port': 8083, 'country': 'DE'},
                    {'host': '127.0.0.1', 'port': 8084, 'country': 'JP'},
                ]
                
                self.proxy_pool = []
                for proxy in mock_proxies:
                    proxy_info = ProxyInfo(
                        host=proxy['host'],
                        port=proxy['port'],
                        country=proxy['country']
                    )
                    self.proxy_pool.append(proxy_info)
            
            logger.info(f"Initialized proxy pool with {len(self.proxy_pool)} proxies")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize proxy pool: {str(e)}")
            return False
    
    def get_current_proxy(self) -> Optional[ProxyInfo]:
        """获取当前代理配置"""
        return self.current_proxy
    
    async def rotate_proxy(self, force: bool = False, exclude_ips: List[str] = None) -> Optional[ProxyInfo]:
        """智能轮换代理IP"""
        try:
            if not self.rotation_enabled:
                return None
                
            current_time = time.time()
            exclude_ips = exclude_ips or []
            
            # 检查是否需要轮换
            if not force and (current_time - self.last_rotation_time) < self.rotation_interval:
                return self.current_proxy
                
            if not self.proxy_pool:
                logger.warning("Proxy pool is empty")
                return None
            
            # 获取可用代理 - 排除已阻塞和指定排除的IP
            available_proxies = []
            for proxy in self.proxy_pool:
                if not proxy.is_available:
                    continue
                if f"{proxy.host}:{proxy.port}" in exclude_ips:
                    continue
                if f"{proxy.host}:{proxy.port}" in self.blocked_ips:
                    continue
                available_proxies.append(proxy)
            
            if not available_proxies:
                logger.warning("No available proxies after filtering")
                return None
            
            # 智能选择策略：优先选择成功率高且最少使用的代理
            available_proxies.sort(key=lambda x: (-x.success_rate, x.success_count + x.failure_count))
            
            # 随机从前50%中选择
            top_half = available_proxies[:max(1, len(available_proxies) // 2)]
            new_proxy = random.choice(top_half)
            
            # 验证代理可用性
            if await self._validate_proxy(new_proxy):
                old_proxy = self.current_proxy
                self.current_proxy = new_proxy
                self.current_proxy.last_used = datetime.now()
                self.last_rotation_time = current_time
                
                logger.info(f"Rotated from {old_proxy.host if old_proxy else 'None'} to {new_proxy.host}:{new_proxy.port}")
                return new_proxy
            else:
                logger.warning(f"Proxy validation failed: {new_proxy.host}:{new_proxy.port}")
                new_proxy.status = ProxyStatus.FAILED
                new_proxy.failure_count += 1
                new_proxy.last_failure = datetime.now()
                return None
                
        except Exception as e:
            logger.error(f"Failed to rotate proxy: {str(e)}")
            return None
    
    async def _validate_proxy(self, proxy: ProxyInfo) -> bool:
        """验证代理可用性"""
        try:
            # 测试模式下直接返回True
            if self.test_mode:
                proxy.success_count += 1
                proxy.response_time = 0.1  # 模拟响应时间
                logger.info(f"Test mode: Proxy validation successful: {proxy.host}:{proxy.port}")
                return True
            
            start_time = time.time()
            proxy_url = f"{proxy.protocol}://{proxy.host}:{proxy.port}"
            
            proxy_config = {'http': proxy_url, 'https': proxy_url}
            if proxy.username and proxy.password:
                auth_proxy_url = f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
                proxy_config = {'http': auth_proxy_url, 'https': auth_proxy_url}
            
            # 测试代理连接
            test_urls = ['http://httpbin.org/ip', 'https://api.ipify.org?format=json']
            
            for test_url in test_urls:
                try:
                    response = requests.get(test_url, proxies=proxy_config, timeout=10)
                    if response.status_code == 200:
                        proxy.response_time = time.time() - start_time
                        proxy.success_count += 1
                        logger.info(f"Proxy validation successful: {proxy.host}:{proxy.port} ({proxy.response_time:.2f}s)")
                        return True
                except Exception:
                    continue
            
            proxy.failure_count += 1
            proxy.last_failure = datetime.now()
            return False
            
        except Exception as e:
            logger.error(f"Proxy validation error: {str(e)}")
            proxy.failure_count += 1
            proxy.last_failure = datetime.now()
            return False
    
    def get_proxy_config_for_playwright(self) -> Optional[Dict[str, Any]]:
        """获取Playwright代理配置"""
        if not self.current_proxy:
            return None
            
        config = {
            'server': f"{self.current_proxy.protocol}://{self.current_proxy.host}:{self.current_proxy.port}"
        }
        
        # 添加认证信息
        if self.current_proxy.username and self.current_proxy.password:
            config['username'] = self.current_proxy.username
            config['password'] = self.current_proxy.password
            
        return config
        
    async def rotate_ip_for_gift_card(self, task_id: str, gift_card_number: str) -> Optional[ProxyInfo]:
        """为礼品卡付款专门轮换IP - 核心功能"""
        try:
            if not self.gift_card_rotation_enabled:
                logger.info(f"Gift card IP rotation disabled for task {task_id}")
                return self.current_proxy
            
            logger.info(f"🎁 Starting IP rotation for gift card {gift_card_number[:4]}**** (task: {task_id})")
            
            # 检查该礼品卡的使用历史
            card_history = self.gift_card_usage_history.get(gift_card_number, [])
            
            # 排除已经用过这张礼品卡的IP
            exclude_ips = [ip for ip in card_history]
            if self.current_proxy:
                current_ip = f"{self.current_proxy.host}:{self.current_proxy.port}"
                # 检查当前IP是否已经使用过太多礼品卡
                current_ip_usage = sum(1 for card_ips in self.gift_card_usage_history.values() 
                                     if current_ip in card_ips)
                
                if current_ip_usage >= self.max_gift_card_per_ip:
                    logger.warning(f"Current IP {current_ip} has been used for {current_ip_usage} gift cards, forcing rotation")
                    exclude_ips.append(current_ip)
            
            # 强制轮换到新IP
            new_proxy = await self.rotate_proxy(force=True, exclude_ips=exclude_ips)
            
            if new_proxy:
                # 记录此IP已用于该礼品卡
                new_ip = f"{new_proxy.host}:{new_proxy.port}"
                if gift_card_number not in self.gift_card_usage_history:
                    self.gift_card_usage_history[gift_card_number] = []
                
                self.gift_card_usage_history[gift_card_number].append(new_ip)
                
                logger.info(f"✅ Successfully rotated to IP {new_ip} for gift card {gift_card_number[:4]}****")
                
                # 保存IP使用历史到文件
                self._save_ip_usage_history()
                
                return new_proxy
            else:
                logger.error(f"❌ Failed to rotate IP for gift card {gift_card_number[:4]}****")
                return None
                
        except Exception as e:
            logger.error(f"Error rotating IP for gift card: {str(e)}")
            return None
    
    def mark_ip_blocked(self, ip_address: str, reason: str = "Apple blocked"):
        """标记IP被封禁"""
        try:
            self.blocked_ips.add(ip_address)
            
            # 更新代理池中对应代理的状态
            for proxy in self.proxy_pool:
                if f"{proxy.host}:{proxy.port}" == ip_address:
                    proxy.status = ProxyStatus.BLOCKED
                    proxy.blocked_until = datetime.now() + timedelta(hours=24)  # 24小时冷却
                    logger.warning(f"🚫 Marked IP {ip_address} as blocked: {reason}")
                    break
                    
        except Exception as e:
            logger.error(f"Error marking IP as blocked: {str(e)}")
    
    def get_gift_card_ip_history(self, gift_card_number: str) -> List[str]:
        """获取礼品卡的IP使用历史"""
        return self.gift_card_usage_history.get(gift_card_number, [])
    
    def _save_ip_usage_history(self):
        """保存IP使用历史到文件"""
        try:
            history_file = "gift_card_ip_history.json"
            with open(history_file, 'w', encoding='utf-8') as f:
                # 只保存卡号的前4位和后4位作为隐私保护
                safe_history = {}
                for card_number, ip_list in self.gift_card_usage_history.items():
                    safe_key = f"{card_number[:4]}****{card_number[-4:]}" if len(card_number) > 8 else card_number[:4] + "****"
                    safe_history[safe_key] = ip_list
                
                json.dump(safe_history, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Failed to save IP usage history: {str(e)}")
    
    def _load_ip_usage_history(self):
        """从文件加载IP使用历史"""
        try:
            history_file = "gift_card_ip_history.json"
            with open(history_file, 'r', encoding='utf-8') as f:
                # 注意：这里加载的是脱敏版本，实际使用时可能需要调整
                loaded_history = json.load(f)
                logger.info(f"Loaded IP usage history with {len(loaded_history)} entries")
                
        except FileNotFoundError:
            logger.info("No existing IP usage history file found")
        except Exception as e:
            logger.error(f"Failed to load IP usage history: {str(e)}")
    
    async def force_rotation_for_task(self, task_id: str) -> bool:
        """为特定任务强制轮换IP"""
        try:
            logger.info(f"Force rotating IP for task {task_id}")
            new_proxy = await self.rotate_proxy(force=True)
            return new_proxy is not None
        except Exception as e:
            logger.error(f"Force rotation failed for task {task_id}: {str(e)}")
            return False
    
    def get_current_ip_info(self) -> Dict[str, Any]:
        """获取当前IP信息"""
        try:
            if self.current_proxy:
                return {
                    'proxy_host': self.current_proxy.host,
                    'proxy_port': self.current_proxy.port,
                    'country': self.current_proxy.country,
                    'status': self.current_proxy.status.value,
                    'success_rate': round(self.current_proxy.success_rate * 100, 2),
                    'response_time': round(self.current_proxy.response_time, 2),
                    'using_proxy': True,
                    'last_used': self.current_proxy.last_used.isoformat() if self.current_proxy.last_used else None
                }
            else:
                # 获取本机IP信息
                try:
                    response = requests.get('https://api.ipify.org?format=json', timeout=5)
                    ip_data = response.json()
                    return {
                        'ip': ip_data.get('ip', 'Unknown'),
                        'country': 'Unknown', 
                        'using_proxy': False
                    }
                except:
                    return {
                        'ip': 'Unknown',
                        'country': 'Unknown',
                        'using_proxy': False
                    }
        except Exception as e:
            logger.error(f"Failed to get IP info: {str(e)}")
            return {'error': str(e)}
    
    def get_proxy_pool_status(self) -> Dict[str, Any]:
        """获取代理池状态"""
        try:
            if not self.proxy_pool:
                return {'total': 0, 'available': 0, 'blocked': 0, 'failed': 0}
            
            status_counts = {}
            for status in ProxyStatus:
                status_counts[status.value] = 0
            
            available_count = 0
            for proxy in self.proxy_pool:
                status_counts[proxy.status.value] += 1
                if proxy.is_available:
                    available_count += 1
            
            return {
                'total': len(self.proxy_pool),
                'available': available_count,
                'by_status': status_counts,
                'blocked_ips': len(self.blocked_ips),
                'gift_cards_tracked': len(self.gift_card_usage_history)
            }
        except Exception as e:
            logger.error(f"Failed to get proxy pool status: {str(e)}")
            return {'error': str(e)}
    
    def cleanup(self):
        """清理资源"""
        self.current_proxy = None
        self.proxy_pool = []
        self.blocked_ips.clear()
        self.gift_card_usage_history.clear()