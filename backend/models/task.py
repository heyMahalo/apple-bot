from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"  
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskStep(Enum):
    INITIALIZING = "initializing"
    NAVIGATING = "navigating"
    CONFIGURING_PRODUCT = "configuring_product"
    ADDING_TO_BAG = "adding_to_bag"
    CHECKOUT = "checkout"
    APPLYING_GIFT_CARD = "applying_gift_card"
    FINALIZING = "finalizing"

@dataclass
class GiftCard:
    """礼品卡数据类"""
    number: str
    expected_status: str = "has_balance"  # has_balance, zero_balance, error
    applied: bool = False  # 是否已应用
    applied_amount: Optional[float] = None  # 实际应用金额
    error_message: Optional[str] = None  # 错误信息

@dataclass
class ProductConfig:
    model: str
    finish: str
    storage: str
    trade_in: str = "No trade-in"
    payment: str = "Buy"
    apple_care: str = "No AppleCare+ Coverage"

@dataclass
class AccountConfig:
    email: str
    password: str
    phone_number: str = '07700900000'

@dataclass
class TaskConfig:
    name: str
    url: str
    product_config: ProductConfig
    account_config: AccountConfig
    enabled: bool = True
    priority: int = 1
    gift_cards: List[GiftCard] = None  # 支持多张礼品卡
    use_proxy: bool = False
    apple_email: Optional[str] = None
    apple_password: Optional[str] = None
    phone_number: Optional[str] = None
    gift_card_code: Optional[str] = None  # 保持向后兼容
    
    def __post_init__(self):
        if self.gift_cards is None:
            self.gift_cards = []

@dataclass
class Task:
    id: str
    config: TaskConfig
    status: TaskStatus = TaskStatus.PENDING
    current_step: Optional[TaskStep] = None
    progress: float = 0.0
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    logs: list = None
    
    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.logs is None:
            self.logs = []
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['status'] = self.status.value
        result['current_step'] = self.current_step.value if self.current_step else None
        result['created_at'] = self.created_at.isoformat() if self.created_at else None
        result['started_at'] = self.started_at.isoformat() if self.started_at else None
        result['completed_at'] = self.completed_at.isoformat() if self.completed_at else None
        return result
    
    def add_log(self, message: str, level: str = "info"):
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message
        }
        self.logs.append(log_entry)
        
    def update_progress(self, step: TaskStep, progress: float):
        self.current_step = step
        self.progress = progress

    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        """从字典创建Task对象"""
        # 重建配置对象
        config_data = data['config']

        account_config = AccountConfig(
            email=config_data['account_config']['email'],
            password=config_data['account_config']['password'],
            phone_number=config_data['account_config'].get('phone_number', '07700900000')
        )

        product_config = ProductConfig(
            model=config_data['product_config']['model'],
            finish=config_data['product_config']['finish'],
            storage=config_data['product_config']['storage'],
            trade_in=config_data['product_config'].get('trade_in', 'No trade-in'),
            payment=config_data['product_config'].get('payment', 'Buy'),
            apple_care=config_data['product_config'].get('apple_care', 'No AppleCare+ Coverage')
        )

        task_config = TaskConfig(
            name=config_data['name'],
            url=config_data['url'],
            account_config=account_config,
            product_config=product_config,
            enabled=config_data.get('enabled', True),
            priority=config_data.get('priority', 1),
            gift_cards=config_data.get('gift_cards'),
            gift_card_code=config_data.get('gift_card_code'),
            use_proxy=config_data.get('use_proxy', False)
        )

        # 创建Task对象
        task = cls(
            id=data['id'],
            config=task_config
        )

        # 设置状态和时间
        task.status = TaskStatus(data['status'])
        task.progress = data.get('progress', 0)
        task.current_step = TaskStep(data['current_step']) if data.get('current_step') else None
        task.error_message = data.get('error_message')

        # 解析时间
        if data.get('created_at'):
            task.created_at = datetime.fromisoformat(data['created_at'])
        if data.get('started_at'):
            task.started_at = datetime.fromisoformat(data['started_at'])
        if data.get('completed_at'):
            task.completed_at = datetime.fromisoformat(data['completed_at'])

        # 重建日志
        task.logs = data.get('logs', [])

        return task