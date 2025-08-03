import sqlite3
import logging
import json
import threading
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
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
                
                # 🚀 创建任务表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        config TEXT NOT NULL,
                        status TEXT NOT NULL,
                        current_step TEXT,
                        progress REAL DEFAULT 0.0,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        error_message TEXT,
                        logs TEXT,
                        celery_task_id TEXT,
                        last_updated TEXT NOT NULL
                    )
                ''')

                # 创建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gift_cards_number ON gift_cards(gift_card_number)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gift_cards_status ON gift_cards(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_last_updated ON tasks(last_updated)')

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

    def add_account(self, email: str, password: str, phone_number: str = "+447700900000", status: str = "可用", notes: str = "") -> int:
        """添加账号（API兼容方法）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # 使用实际的表结构（没有status和notes字段）
                cursor.execute('''
                    INSERT INTO accounts (email, password, phone_number, created_at, updated_at, is_active)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                ''', (email, password, phone_number))
                conn.commit()
                account_id = cursor.lastrowid
                logger.info(f"账号添加成功: {email} (ID: {account_id})")
                return account_id
        except Exception as e:
            logger.error(f"添加账号失败: {str(e)}")
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

    def update_account_status_by_email(self, email: str, status: str, notes: str = None) -> bool:
        """根据邮箱更新账号状态"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 构建更新语句
                update_fields = ['status = ?']
                params = [status]

                if notes is not None:
                    update_fields.append('notes = ?')
                    params.append(notes)

                # 添加更新时间
                update_fields.append('updated_at = CURRENT_TIMESTAMP')
                params.append(email)  # WHERE条件的参数

                query = f'''
                    UPDATE accounts
                    SET {', '.join(update_fields)}
                    WHERE email = ? AND deleted_at IS NULL
                '''

                cursor.execute(query, params)
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"账号状态更新成功: {email} -> {status}")
                    return True
                else:
                    logger.warning(f"未找到邮箱为 {email} 的账号")
                    return False

        except Exception as e:
            logger.error(f"更新账号状态失败: {str(e)}")
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

    def get_gift_card_by_number(self, gift_card_number: str) -> Optional[GiftCard]:
        """根据礼品卡号码获取礼品卡"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM gift_cards WHERE gift_card_number = ?', (gift_card_number,))
                row = cursor.fetchone()

                return self._row_to_gift_card(row) if row else None

        except Exception as e:
            logger.error(f"根据号码获取礼品卡失败: {str(e)}")
            return None

    def update_gift_card_status(self, gift_card_number: str, status: str) -> bool:
        """根据礼品卡号码更新状态"""
        try:
            # 验证状态
            valid_statuses = [status.value for status in GiftCardStatus]
            if status not in valid_statuses:
                raise ValueError(f"无效的礼品卡状态: {status}")

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE gift_cards
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE gift_card_number = ?
                ''', (status, gift_card_number))

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"更新礼品卡状态失败: {str(e)}")
            return False

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

    # ==================== 任务管理 ====================

    def save_task(self, task_dict: Dict[str, Any]) -> bool:
        """保存或更新任务"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 准备数据
                task_data = {
                    'id': task_dict['id'],
                    'config': json.dumps(task_dict['config']),
                    'status': task_dict['status'],
                    'current_step': task_dict.get('current_step'),
                    'progress': task_dict.get('progress', 0.0),
                    'created_at': task_dict['created_at'],
                    'started_at': task_dict.get('started_at'),
                    'completed_at': task_dict.get('completed_at'),
                    'error_message': task_dict.get('error_message'),
                    'logs': json.dumps(task_dict.get('logs', [])),
                    'celery_task_id': task_dict.get('celery_task_id'),
                    'last_updated': datetime.now().isoformat()
                }

                # 使用REPLACE INTO进行插入或更新
                cursor.execute('''
                    REPLACE INTO tasks (
                        id, config, status, current_step, progress,
                        created_at, started_at, completed_at, error_message,
                        logs, celery_task_id, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_data['id'], task_data['config'], task_data['status'],
                    task_data['current_step'], task_data['progress'],
                    task_data['created_at'], task_data['started_at'],
                    task_data['completed_at'], task_data['error_message'],
                    task_data['logs'], task_data['celery_task_id'],
                    task_data['last_updated']
                ))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"❌ 保存任务失败: {task_dict.get('id', 'unknown')} - {e}")
            return False

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取单个任务"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
                row = cursor.fetchone()

                if row:
                    return self._row_to_task_dict(row)
                return None

        except Exception as e:
            logger.error(f"❌ 获取任务失败: {task_id} - {e}")
            return None

    def get_all_tasks(self, limit: int = None, offset: int = 0) -> List[Dict[str, Any]]:
        """获取所有任务"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                query = 'SELECT * FROM tasks ORDER BY created_at DESC'
                params = []

                if limit:
                    query += ' LIMIT ? OFFSET ?'
                    params.extend([limit, offset])

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [self._row_to_task_dict(row) for row in rows]

        except Exception as e:
            logger.error(f"❌ 获取所有任务失败: {e}")
            return []

    def delete_task(self, task_id: str) -> bool:
        """从数据库中删除任务"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
                conn.commit()

                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"✅ 任务已从数据库删除: {task_id}")
                    return True
                else:
                    logger.warning(f"⚠️ 数据库中未找到任务: {task_id}")
                    return False

        except Exception as e:
            logger.error(f"❌ 从数据库删除任务失败: {task_id} - {e}")
            return False

    def get_tasks_by_status(self, status: str) -> List[Dict[str, Any]]:
        """根据状态获取任务"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    'SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC',
                    (status,)
                )
                rows = cursor.fetchall()

                return [self._row_to_task_dict(row) for row in rows]

        except Exception as e:
            logger.error(f"❌ 根据状态获取任务失败: {status} - {e}")
            return []

    def get_task_stats(self) -> Dict[str, int]:
        """获取任务统计信息"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM tasks
                    GROUP BY status
                ''')

                stats = {'total': 0, 'pending': 0, 'running': 0, 'completed': 0, 'failed': 0, 'cancelled': 0}

                for row in cursor.fetchall():
                    status, count = row
                    if status in stats:
                        stats[status] = count
                    stats['total'] += count

                return stats

        except Exception as e:
            logger.error(f"❌ 获取任务统计失败: {e}")
            return {'total': 0, 'pending': 0, 'running': 0, 'completed': 0, 'failed': 0, 'cancelled': 0}

    def _row_to_task_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将数据库行转换为任务字典"""
        try:
            task_dict = {
                'id': row['id'],
                'config': json.loads(row['config']) if row['config'] else {},
                'status': row['status'],
                'current_step': row['current_step'],
                'progress': row['progress'] or 0.0,
                'created_at': row['created_at'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
                'error_message': row['error_message'],
                'logs': json.loads(row['logs']) if row['logs'] else [],
                'celery_task_id': row['celery_task_id'],
                'last_updated': row['last_updated']
            }
            return task_dict

        except Exception as e:
            logger.error(f"❌ 转换数据库行失败: {e}")
            return {}
