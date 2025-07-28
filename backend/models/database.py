import sqlite3
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import os

logger = logging.getLogger(__name__)

class GiftCardStatus(Enum):
    """礼品卡状态枚举"""
    HAS_BALANCE = "有额度"
    ZERO_BALANCE = "0余额"
    NON_LOCAL_CARD = "非本国卡"
    RECHARGED = "被充值"

@dataclass
class Account:
    """账号模型"""
    id: Optional[int] = None
    email: str = ""
    password: str = ""
    phone_number: str = ""  # 英国电话号码格式
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_active: bool = True

@dataclass
class GiftCard:
    """礼品卡模型"""
    id: Optional[int] = None
    gift_card_number: str = ""
    status: str = GiftCardStatus.HAS_BALANCE.value
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_active: bool = True
    notes: str = ""  # 备注信息

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str = "apple_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建账号表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        phone_number TEXT NOT NULL DEFAULT '+447700900000',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1
                    )
                ''')

                # 检查并添加phone_number字段（如果表已存在但没有此字段）
                cursor.execute("PRAGMA table_info(accounts)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'phone_number' not in columns:
                    cursor.execute('ALTER TABLE accounts ADD COLUMN phone_number TEXT NOT NULL DEFAULT "+447700900000"')
                    logger.info("已添加phone_number字段到accounts表")
                
                # 创建礼品卡表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gift_cards (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        gift_card_number TEXT UNIQUE NOT NULL,
                        status TEXT NOT NULL DEFAULT '有额度',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1,
                        notes TEXT DEFAULT ''
                    )
                ''')
                
                # 创建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gift_cards_number ON gift_cards(gift_card_number)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gift_cards_status ON gift_cards(status)')
                
                conn.commit()
                logger.info("数据库初始化成功")
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
            raise
    
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
        return conn
    
    # ==================== 账号管理 ====================
    
    def create_account(self, email: str, password: str, phone_number: str = "+447700900000") -> Account:
        """创建账号"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO accounts (email, password, phone_number)
                    VALUES (?, ?, ?)
                ''', (email, password, phone_number))

                account_id = cursor.lastrowid
                conn.commit()

                # 返回创建的账号
                return self.get_account_by_id(account_id)

        except sqlite3.IntegrityError:
            raise ValueError(f"邮箱 {email} 已存在")
        except Exception as e:
            logger.error(f"创建账号失败: {str(e)}")
            raise
    
    def get_all_accounts(self, active_only: bool = True) -> List[Account]:
        """获取所有账号"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if active_only:
                    cursor.execute('SELECT * FROM accounts WHERE is_active = 1 ORDER BY created_at DESC')
                else:
                    cursor.execute('SELECT * FROM accounts ORDER BY created_at DESC')
                
                rows = cursor.fetchall()
                return [self._row_to_account(row) for row in rows]
                
        except Exception as e:
            logger.error(f"获取账号列表失败: {str(e)}")
            return []
    
    def get_account_by_id(self, account_id: int) -> Optional[Account]:
        """根据ID获取账号"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
                row = cursor.fetchone()
                
                return self._row_to_account(row) if row else None
                
        except Exception as e:
            logger.error(f"获取账号失败: {str(e)}")
            return None
    
    def update_account(self, account_id: int, email: str = None, password: str = None, phone_number: str = None) -> bool:
        """更新账号"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                updates = []
                params = []

                if email is not None:
                    updates.append("email = ?")
                    params.append(email)

                if password is not None:
                    updates.append("password = ?")
                    params.append(password)

                if phone_number is not None:
                    updates.append("phone_number = ?")
                    params.append(phone_number)

                if not updates:
                    return True

                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(account_id)

                query = f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, params)
                conn.commit()

                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"更新账号失败: {str(e)}")
            return False
    
    def delete_account(self, account_id: int) -> bool:
        """删除账号（软删除）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE accounts 
                    SET is_active = 0, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (account_id,))
                conn.commit()
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"删除账号失败: {str(e)}")
            return False
    
    # ==================== 礼品卡管理 ====================
    
    def create_gift_card(self, gift_card_number: str, status: str = GiftCardStatus.HAS_BALANCE.value, notes: str = "") -> GiftCard:
        """创建礼品卡"""
        try:
            # 验证状态
            valid_statuses = [status.value for status in GiftCardStatus]
            if status not in valid_statuses:
                raise ValueError(f"无效的礼品卡状态: {status}")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO gift_cards (gift_card_number, status, notes)
                    VALUES (?, ?, ?)
                ''', (gift_card_number, status, notes))
                
                card_id = cursor.lastrowid
                conn.commit()
                
                # 返回创建的礼品卡
                return self.get_gift_card_by_id(card_id)
                
        except sqlite3.IntegrityError:
            raise ValueError(f"礼品卡号 {gift_card_number} 已存在")
        except Exception as e:
            logger.error(f"创建礼品卡失败: {str(e)}")
            raise
    
    def get_all_gift_cards(self, active_only: bool = True, status_filter: str = None) -> List[GiftCard]:
        """获取所有礼品卡"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM gift_cards"
                params = []
                conditions = []
                
                if active_only:
                    conditions.append("is_active = 1")
                
                if status_filter:
                    conditions.append("status = ?")
                    params.append(status_filter)
                
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY created_at DESC"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._row_to_gift_card(row) for row in rows]
                
        except Exception as e:
            logger.error(f"获取礼品卡列表失败: {str(e)}")
            return []
    
    def get_gift_card_by_id(self, card_id: int) -> Optional[GiftCard]:
        """根据ID获取礼品卡"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM gift_cards WHERE id = ?', (card_id,))
                row = cursor.fetchone()
                
                return self._row_to_gift_card(row) if row else None
                
        except Exception as e:
            logger.error(f"获取礼品卡失败: {str(e)}")
            return None
    
    def update_gift_card(self, card_id: int, gift_card_number: str = None, status: str = None, notes: str = None) -> bool:
        """更新礼品卡"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                updates = []
                params = []
                
                if gift_card_number is not None:
                    updates.append("gift_card_number = ?")
                    params.append(gift_card_number)
                
                if status is not None:
                    # 验证状态
                    valid_statuses = [s.value for s in GiftCardStatus]
                    if status not in valid_statuses:
                        raise ValueError(f"无效的礼品卡状态: {status}")
                    updates.append("status = ?")
                    params.append(status)
                
                if notes is not None:
                    updates.append("notes = ?")
                    params.append(notes)
                
                if not updates:
                    return True
                
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(card_id)
                
                query = f"UPDATE gift_cards SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, params)
                conn.commit()
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"更新礼品卡失败: {str(e)}")
            return False
    
    def delete_gift_card(self, card_id: int) -> bool:
        """删除礼品卡（软删除）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE gift_cards 
                    SET is_active = 0, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (card_id,))
                conn.commit()
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"删除礼品卡失败: {str(e)}")
            return False
    
    # ==================== 辅助方法 ====================
    
    def _row_to_account(self, row) -> Account:
        """将数据库行转换为Account对象"""
        # 处理可能不存在的phone_number字段
        try:
            phone_number = row['phone_number']
        except (KeyError, IndexError):
            phone_number = '+447700900000'  # 默认英国号码

        return Account(
            id=row['id'],
            email=row['email'],
            password=row['password'],
            phone_number=phone_number,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            is_active=bool(row['is_active'])
        )
    
    def _row_to_gift_card(self, row) -> GiftCard:
        """将数据库行转换为GiftCard对象"""
        return GiftCard(
            id=row['id'],
            gift_card_number=row['gift_card_number'],
            status=row['status'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            is_active=bool(row['is_active']),
            notes=row['notes']
        )
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 账号统计
                cursor.execute('SELECT COUNT(*) FROM accounts WHERE is_active = 1')
                active_accounts = cursor.fetchone()[0]
                
                # 礼品卡统计
                cursor.execute('SELECT status, COUNT(*) FROM gift_cards WHERE is_active = 1 GROUP BY status')
                gift_card_stats = dict(cursor.fetchall())
                
                cursor.execute('SELECT COUNT(*) FROM gift_cards WHERE is_active = 1')
                total_gift_cards = cursor.fetchone()[0]
                
                return {
                    'accounts': {
                        'total': active_accounts
                    },
                    'gift_cards': {
                        'total': total_gift_cards,
                        'by_status': gift_card_stats
                    }
                }
                
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return {}
