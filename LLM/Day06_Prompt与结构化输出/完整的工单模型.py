from enum import Enum

from pydantic import BaseModel, Field, ValidationError, field_validator


#Enum:枚举
class TicketType(str, Enum):
    # 工单业务分类的允许值
    logistics = "物流咨询"
    refund = "退款售后"
    product = "商品故障"
    other = "其他"

class Urgency(str, Enum):
    # 工单紧急程度的允许值
    normal = "普通"
    urgent = "紧急"


# BaseModel,模型
class TicketExtraction(BaseModel):
    # 工单所属的业务分类，只能使用 TicketType 中的值
    ticket_type: TicketType
    # 工单紧急程度，只能是普通或紧急
    urgency: Urgency

    #Field:给模型字段加规则
    # 原文明示的订单号；原文没有时返回 None
    order_id: str | None = Field(
        description="原文明示的订单号；没有时返回 null",
    )
    # 对工单问题的简短概括，不能增加原文没有的事实
    summary: str = Field(
        min_length=1,
        max_length=80,
        description="工单摘要；不增加原文没有的事实",
    )
    # 后续处理仍然缺少的信息，例如订单号
    missing_information: list[str]
    # 当前结果是否需要人工确认
    needs_human_review: bool
    # 转人工的原因；不需要转人工时返回 None
    review_reason: str | None

    #字段验证器
    @field_validator("order_id")
    @classmethod
    def normalize_order_id(cls, value):
        # 统一去除订单号两端空格并转换为大写
        if value is None:
            return None
        #cleaned={} -> None
        cleaned = value.strip().upper()
        return cleaned or None


# 构造一条合法数据，观察清洗和序列化结果
valid_ticket = TicketExtraction(
    ticket_type="物流咨询",
    urgency="普通",
    order_id=" a102 ",
    summary="客户查询物流进度",
    missing_information=[],
    needs_human_review=False,
    review_reason=None,
)

print(valid_ticket.order_id)
print(valid_ticket.model_dump_json(indent=2))


try:
    # 故意传入错误枚举和空摘要，观察 Pydantic 校验错误
    TicketExtraction(
        ticket_type="无法识别",
        urgency="非常着急",
        order_id=None,
        summary="",
        missing_information=[],
        needs_human_review=False,
        review_reason=None,
    )
except ValidationError as error:
    print("校验失败")
    for item in error.errors():
        print(item["loc"], item["type"])

# 查看模型生成的 JSON Schema 及必填字段
schema = TicketExtraction.model_json_schema()
print("必填字段：", schema["required"])





















































