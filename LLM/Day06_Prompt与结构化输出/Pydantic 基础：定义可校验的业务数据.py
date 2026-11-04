from pydantic import BaseModel, ValidationError, Field, field_validator
from enum import Enum

# Pydantic 模型 + 枚举 + 校验

# 定义工单类型枚举,枚举值是字符串
class TicketType(str, Enum):
    #业务允许的工单类型
    logistics = '物流咨询',
    refund = '退款售后',
    product = '商品故障',
    other = '其他'

# 定义 Pydantic 模型
class TicketFieldDemo(BaseModel):
    # 只能使用 TicketType 中定义的业务分类
    ticket_type: TicketType
    # 后续处理仍然缺少的信息
    missing_information: list[str]
    # 是否需要人工确认
    needs_human_review: bool

# 区分必填、可空和默认值
class FieldStateDemo(BaseModel):
    # 必填且不能为 None
    title: str
    # 必填，但允许传入 None
    note: str | None
    # 可以省略；省略时默认使用 None
    comment: str | None = None

# 用 `Field` 补充说明和约束
class FieldDemo(BaseModel):
    #description 会说明字段的业务含义
    order_id: str | None = Field(
        min_length=1,
        max_length=80,
        description='工单摘要: 不增加原文没有的事实'
    )

# 用字段验证器检查或转换值(BaseModel:定义 Pydantic模型)
class OrderDemo(BaseModel):
    #Pydantic 模型字段必须保留类型注解，否则不认为是字段
    order_id: str | None

    @field_validator('order_id')
    @classmethod
    def normalize_order_id(cls, value):
        #没有订单号时保持 None
        # 去除两端空格并统一转换为大写
        if value is None:
            return None
        cleaned = value.strip().upper()
        #cleaned={}=None
        return cleaned or None


# #合法输入，创建模型实例
# demo = TicketFieldDemo(
#     ticket_type="物流咨询",
#     missing_information=["订单号"],
#     needs_human_review=False,
# )
# # 序列化成 JSON 并打印， 输出json字符串
# print(demo.model_dump_json(indent=2))
#
# # 非法输入，捕获校验错误
# try:
#     TicketFieldDemo(
#         ticket_type="投诉建议",
#         missing_information=[],
#         needs_human_review=True,
#     )
# except ValidationError as error:
#     #取第一个错误, loc:错误位置, type:错误类型
#     print(error.errors()[0]["loc"], error.errors()[0]["type"])



ticket = OrderDemo(order_id='')
print(ticket.order_id)









































