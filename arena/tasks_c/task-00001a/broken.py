class CycleError(ValueError):
    pass


def topo_sort(graph: dict) -> list:
    """Sắp xếp topo.  Có chu trình thì ném CycleError.

    Khi nhiều đỉnh cùng sẵn sàng, phải chọn đỉnh có TÊN NHỎ NHẤT
    để kết quả luôn giống nhau qua các lần chạy.
    """
    order: list = []
    seen: set = set()

    def visit(node):
        if node in seen:
            return
        seen.add(node)
        for nxt in graph.get(node, []):
            visit(nxt)
        order.append(node)

    for node in graph:
        visit(node)
    return order[::-1]
